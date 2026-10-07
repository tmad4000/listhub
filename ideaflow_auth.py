"""Independent first-party OIDC login; legacy Noos identity remains unchanged."""
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

import jwt
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from nanoid import generate
from db import get_db
from models import User

ideaflow_bp = Blueprint('ideaflow', __name__)
ISSUER = 'https://id.ideaflow.app/api/auth'


def config():
    path = os.environ.get('LISTHUB_IDEAFLOW_CONFIG')
    if not path:
        return None
    with open(path) as source:
        cfg = json.load(source)
    if cfg.get('issuer') != ISSUER or not cfg.get('client_id') or not cfg.get('client_secret'):
        raise RuntimeError('Invalid ListHub Ideaflow client configuration')
    return cfg


def local_next(value):
    return value if value and value.startswith('/') and not value.startswith('//') and '\\' not in value and not any(ord(c) < 32 for c in value) else '/dash'


def enabled():
    return config() is not None


def start(silent=False, choose=False):
    cfg = config()
    if not cfg:
        return redirect(url_for('auth.noos_login'))
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    next_path = local_next(request.args.get('next'))
    session['ideaflow_pending'] = dict(state=state, nonce=nonce, verifier=verifier, created=time.time(), next=next_path, silent=silent)
    params = dict(client_id=cfg['client_id'], redirect_uri=cfg['redirect_uris'][0], response_type='code', scope='openid email profile', state=state, nonce=nonce, code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='), code_challenge_method='S256')
    if choose or session.get('ideaflow_signed_out'):
        params['prompt'] = 'select_account'
    elif silent:
        params['prompt'] = 'none'
    return redirect(ISSUER + '/oauth2/authorize?' + urllib.parse.urlencode(params))


@ideaflow_bp.route('/auth/ideaflow/login')
def login():
    return start()


@ideaflow_bp.route('/auth/ideaflow/switch-account')
def switch_account():
    logout_user()
    session['ideaflow_signed_out'] = True
    return start(choose=True)


def exchange(code, pending, cfg):
    body = urllib.parse.urlencode(dict(grant_type='authorization_code', code=code, redirect_uri=cfg['redirect_uris'][0], code_verifier=pending['verifier'], client_id=cfg['client_id'], client_secret=cfg['client_secret'])).encode()
    req = urllib.request.Request(ISSUER + '/oauth2/token', data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    with urllib.request.urlopen(req, timeout=12) as response:
        tokens = json.load(response)
    signing = jwt.PyJWKClient(ISSUER + '/jwks', timeout=12).get_signing_key_from_jwt(tokens['id_token'])
    claims = jwt.decode(tokens['id_token'], signing.key, algorithms=['EdDSA'], audience=cfg['client_id'], issuer=ISSUER, options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'nonce']})
    if not secrets.compare_digest(claims['nonce'], pending['nonce']):
        raise ValueError('Nonce mismatch')
    if not isinstance(claims['sub'], str) or not claims['sub']:
        raise ValueError('Missing subject')
    if isinstance(claims['aud'], list) and len(claims['aud']) > 1 and claims.get('azp') != cfg['client_id']:
        raise ValueError('Authorized party mismatch')
    return claims


def resolve_user(claims):
    db = get_db()
    db.execute('BEGIN IMMEDIATE')
    try:
        mapping = db.execute('SELECT user_id FROM ideaflow_identity WHERE issuer=? AND subject=?', (ISSUER, claims['sub'])).fetchone()
        if mapping:
            user = User.get(db, mapping['user_id'])
            if not user:
                raise ValueError('Identity account unavailable')
            db.commit()
            return user
        email = claims.get('email', '')
        if claims.get('email_verified') is not True or not isinstance(email, str) or not email:
            raise ValueError('Verified email required')
        matches = db.execute('SELECT * FROM user WHERE lower(email)=lower(?)', (email,)).fetchall()
        if len(matches) > 1:
            raise ValueError('Account match requires support')
        if matches:
            # Never attach an identity to an existing legacy account on email alone.
            raise ValueError('Existing ListHub account requires explicit linking. Sign in with Noos or your local password first, then connect Ideaflow from your account menu.')
        username = ''.join(c for c in email.split('@')[0].lower() if c.isalnum())[:20] or 'user'
        base, suffix = username, 1
        while User.get_by_username(db, username):
            username, suffix = base + str(suffix), suffix + 1
        user_id = generate()
        db.execute('INSERT INTO user (id,username,display_name,email,password_hash) VALUES (?,?,?,?,?)', (user_id, username, claims.get('name') or username, email.lower(), '!ideaflow-oidc'))
        db.execute('INSERT INTO ideaflow_identity (issuer,subject,user_id) VALUES (?,?,?)', (ISSUER, claims['sub'], user_id))
        db.commit()
        try:
            from git_backend import init_user_repo
            init_user_repo(username)
        except Exception:
            current_app.logger.warning('New account git repo initialization deferred')
        return User.get(db, user_id)
    except Exception:
        db.rollback()
        raise


@ideaflow_bp.route('/auth/ideaflow/link', methods=['POST'])
def link():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login_local'))
    response = start(choose=True)
    session['ideaflow_pending']['link_user_id'] = current_user.id
    session.modified = True
    return response


@ideaflow_bp.route('/auth/ideaflow/callback')
def callback():
    pending = session.pop('ideaflow_pending', None)
    if not pending or time.time() - pending['created'] > 300 or not request.args.get('state') or not secrets.compare_digest(request.args['state'], pending['state']):
        flash('Sign-in expired. Please try again.', 'error')
        return redirect('/login?auto=off')
    if request.args.get('error'):
        if pending['silent']:
            session['ideaflow_auto_attempted'] = True
        else:
            flash('Sign-in was cancelled or unavailable.', 'error')
        return redirect('/login?auto=off')
    try:
        claims = exchange(request.args['code'], pending, config())
        if pending.get('link_user_id'):
            if not current_user.is_authenticated or current_user.id != pending['link_user_id']:
                raise ValueError('Sign in to the original ListHub account again before linking')
            db = get_db()
            db.execute('BEGIN IMMEDIATE')
            try:
                existing = db.execute('SELECT user_id FROM ideaflow_identity WHERE issuer=? AND subject=?', (ISSUER, claims['sub'])).fetchone()
                local = db.execute('SELECT subject FROM ideaflow_identity WHERE issuer=? AND user_id=?', (ISSUER, current_user.id)).fetchone()
                if (existing and existing['user_id'] != current_user.id) or (local and local['subject'] != claims['sub']):
                    raise ValueError('This account is already connected to another identity')
                db.execute('INSERT OR IGNORE INTO ideaflow_identity (issuer,subject,user_id) VALUES (?,?,?)', (ISSUER, claims['sub'], current_user.id))
                db.commit()
            except Exception:
                db.rollback()
                raise
            user = current_user
        else:
            user = resolve_user(claims)
        login_user(user, remember=True)
        session.pop('ideaflow_signed_out', None)
        session.pop('ideaflow_auto_attempted', None)
        return redirect(pending['next'])
    except ValueError as error:
        flash(str(error), 'error')
    except Exception:
        flash('Ideaflow sign-in could not finish. Please try again.', 'error')
    return redirect('/login?auto=off')
