import functools
import hashlib
import os
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
import json
from urllib.parse import parse_qs, urlparse

import bcrypt
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, request, redirect, url_for, render_template, flash, jsonify, session, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from flask_login import user_logged_in, user_logged_out
from nanoid import generate as nanoid

from db import get_db
from models import User

auth_bp = Blueprint('auth', __name__)
oauth = OAuth()

ADMIN_TOKEN = os.environ.get('LISTHUB_ADMIN_TOKEN', '')
NOOS_AUTH_URL = os.environ.get('NOOS_AUTH_URL', 'https://globalbr.ai')  # For browser redirects
NOOS_INTERNAL_URL = os.environ.get('NOOS_INTERNAL_URL', 'http://localhost:4000')  # For server-to-server
NOOS_CLIENT_ID = 'listhub'
LISTHUB_PUBLIC_URL = os.environ.get('LISTHUB_PUBLIC_URL', 'https://listhub.globalbr.ai')
_IDEAFLOW_CONTEXTS_KEY = 'ideaflow_oauth_contexts'
_IDEAFLOW_STATE_PREFIX = '_state_ideaflow_'
_IDEAFLOW_SESSION_KEY = 'ideaflow_link_session'
_IDEAFLOW_CONTEXT_TTL = 600
_IDEAFLOW_MAX_CONTEXTS = 3


def ideaflow_oidc_enabled(config):
    """Fail closed unless the kill flag and both client credentials exist."""
    return bool(
        config.get('IDEAFLOW_OIDC_ENABLED')
        and config.get('IDEAFLOW_OIDC_CLIENT_ID')
        and config.get('IDEAFLOW_OIDC_CLIENT_SECRET')
    )


def init_oauth(app):
    oauth.init_app(app)
    user_logged_in.connect(_reset_ideaflow_link_session, app)
    user_logged_out.connect(_reset_ideaflow_link_session, app)
    if ideaflow_oidc_enabled(app.config):
        oauth.register(
            name='ideaflow',
            server_metadata_url=app.config['IDEAFLOW_OIDC_DISCOVERY_URL'],
            client_id=app.config['IDEAFLOW_OIDC_CLIENT_ID'],
            client_secret=app.config['IDEAFLOW_OIDC_CLIENT_SECRET'],
            client_kwargs={
                'scope': 'openid email profile',
                'token_endpoint_auth_method': 'client_secret_basic',
                'code_challenge_method': 'S256',
                'default_timeout': 5,
            },
        )


def _safe_next_url(value=None):
    target = (value if value is not None else request.args.get('next', '')).strip()
    parsed = urlparse(target)
    if (
        target.startswith('/')
        and not target.startswith('//')
        and '\\' not in target
        and not parsed.scheme
        and not parsed.netloc
        and len(target) <= 512
    ):
        return target
    return url_for('views.dashboard')


def _ideaflow_client():
    if not ideaflow_oidc_enabled(current_app.config):
        return None
    return getattr(oauth, 'ideaflow', None)


def _ideaflow_enabled_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not ideaflow_oidc_enabled(current_app.config):
            abort(404)
        return view(*args, **kwargs)
    return wrapped


def _ideaflow_callback_url():
    return current_app.config['LISTHUB_PUBLIC_URL'] + url_for('auth.ideaflow_callback')


def _save_ideaflow_contexts(pending):
    if pending:
        session[_IDEAFLOW_CONTEXTS_KEY] = pending
    else:
        session.pop(_IDEAFLOW_CONTEXTS_KEY, None)


def _prune_ideaflow_contexts():
    now = time.time()
    pending = {
        state: context
        for state, context in session.get(_IDEAFLOW_CONTEXTS_KEY, {}).items()
        if context.get('expires_at', 0) > now
        and session.get(_IDEAFLOW_STATE_PREFIX + state, {}).get('exp', 0) > now
    }
    pending = dict(sorted(
        pending.items(), key=lambda item: item[1]['expires_at'],
    )[-_IDEAFLOW_MAX_CONTEXTS:])
    for key in list(session):
        if key.startswith(_IDEAFLOW_STATE_PREFIX) and key[len(_IDEAFLOW_STATE_PREFIX):] not in pending:
            session.pop(key, None)
    _save_ideaflow_contexts(pending)
    return pending


def _reset_ideaflow_link_session(sender, **kwargs):
    session.pop(_IDEAFLOW_SESSION_KEY, None)
    pending = dict(session.get(_IDEAFLOW_CONTEXTS_KEY, {}))
    for state, context in list(pending.items()):
        if context.get('mode') == 'link':
            pending.pop(state)
            session.pop(_IDEAFLOW_STATE_PREFIX + state, None)
    _save_ideaflow_contexts(pending)


def _stash_ideaflow_context(state, context):
    if not state:
        raise ValueError('Missing Ideaflow authorization state')
    expires_at = time.time() + _IDEAFLOW_CONTEXT_TTL
    pending = dict(session.get(_IDEAFLOW_CONTEXTS_KEY, {}))
    pending[state] = {**context, 'expires_at': expires_at}
    state_key = _IDEAFLOW_STATE_PREFIX + state
    session[state_key] = {**session[state_key], 'exp': expires_at}
    _save_ideaflow_contexts(pending)
    _prune_ideaflow_contexts()


def _pop_ideaflow_context():
    pending = _prune_ideaflow_contexts()
    state = request.args.get('state', '').strip()
    if not state:
        return None
    context = pending.pop(state, None)
    _save_ideaflow_contexts(pending)
    return context


def hash_api_key(raw_key):
    """Hash an API key with SHA-256 for fast lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def require_api_auth(f):
    """Decorator: authenticate via Bearer token, admin token, or session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated:
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            raw_key = auth_header[7:]
            db = get_db()

            # Check admin token (used by post-receive hooks)
            # Admin token requires X-ListHub-User header to identify the user
            if ADMIN_TOKEN and raw_key == ADMIN_TOKEN:
                target_user = request.headers.get('X-ListHub-User', '')
                if target_user:
                    if '@' in target_user:
                        user = User.get_by_email(db, target_user)
                    else:
                        user = User.get_by_username(db, target_user)
                else:
                    # For backwards compat, try JSON body
                    user = None
                if user:
                    request._api_user = user
                    request._api_scopes = ['read', 'write', 'sync']
                    return f(*args, **kwargs)

            # Check API key
            key_h = hash_api_key(raw_key)
            user = User.get_by_api_key(db, key_h)
            if user:
                row = db.execute(
                    "SELECT scopes FROM api_key WHERE key_hash = ?", (key_h,)
                ).fetchone()
                request._api_user = user
                request._api_scopes = (row['scopes'] or 'read').split(',') if row else ['read']
                return f(*args, **kwargs)

        return jsonify({"error": "Authentication required"}), 401

    return decorated


def get_current_api_user():
    """Get the authenticated user (session or API key)."""
    if current_user.is_authenticated:
        return current_user
    return getattr(request, '_api_user', None)


def api_has_scope(scope):
    """Check if current API key has a given scope."""
    if current_user.is_authenticated:
        return True  # Session users have all scopes
    scopes = getattr(request, '_api_scopes', [])
    return scope in scopes


@auth_bp.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    if ideaflow_oidc_enabled(current_app.config):
        return render_template('login_choice.html', next_url=_safe_next_url())
    return redirect(url_for('auth.noos_login'))


@auth_bp.route('/login/local', methods=['GET', 'POST'])
def login_local():
    """Local username/password login (fallback for accounts without Noos)."""
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        user = User.get_by_username(db, username)

        if user and user.password_hash and user.password_hash.startswith('$2'):
            try:
                if bcrypt.checkpw(password.encode(), user.password_hash.encode()):
                    login_user(user, remember=True)
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('views.dashboard'))
            except Exception:
                pass

        flash('Invalid username or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('views.landing'))


@auth_bp.route('/auth/noos/login')
def noos_login():
    """Redirect to Noos OAuth authorize page."""
    if not NOOS_AUTH_URL:
        flash('Noos login is not configured.', 'error')
        return redirect(url_for('auth.login'))

    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state

    redirect_uri = LISTHUB_PUBLIC_URL + '/auth/noos/callback'

    params = urllib.parse.urlencode({
        'client_id': NOOS_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'state': state,
    })
    return redirect(f'{NOOS_AUTH_URL}/auth/authorize?{params}')


@auth_bp.route('/auth/noos/callback')
def noos_callback():
    """Handle Noos OAuth callback — exchange code for user info, find or create user."""
    error = request.args.get('error')
    if error:
        flash(f'Noos login failed: {error}', 'error')
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    state = request.args.get('state')

    # Verify state
    saved_state = session.pop('oauth_state', None)
    if not state or state != saved_state:
        flash('Login failed: state mismatch.', 'error')
        return redirect(url_for('auth.login'))

    if not code:
        flash('Login failed: no authorization code.', 'error')
        return redirect(url_for('auth.login'))

    # Exchange code for user info via Noos sso-exchange
    try:
        payload = json.dumps({'code': code}).encode()
        req = urllib.request.Request(
            f'{NOOS_INTERNAL_URL}/api/auth/sso-exchange',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        flash(f'Noos login failed: could not exchange code.', 'error')
        return redirect(url_for('auth.login'))

    noos_user = data.get('user', {})
    noos_id = noos_user.get('id')
    noos_email = noos_user.get('email', '')
    noos_name = noos_user.get('name', '')

    if not noos_id:
        flash('Noos login failed: no user ID returned.', 'error')
        return redirect(url_for('auth.login'))

    db = get_db()

    # 1. Try to find existing ListHub user linked by noos_id
    user = User.get_by_noos_id(db, noos_id)

    # 2. If not linked, try to match by email
    if not user and noos_email:
        user = User.get_by_email(db, noos_email)
        if user:
            # Link existing account to Noos
            db.execute("UPDATE user SET noos_id = ? WHERE id = ?", (noos_id, user.id))
            db.commit()

    # 3. Auto-create a new ListHub account
    if not user:
        # Generate username from email or name
        base_username = noos_email.split('@')[0] if noos_email else noos_name.lower().replace(' ', '')
        base_username = ''.join(c for c in base_username if c.isalnum())[:20]
        if not base_username or len(base_username) < 2:
            base_username = 'user'

        # Ensure uniqueness
        username = base_username
        suffix = 1
        while User.get_by_username(db, username):
            username = f'{base_username}{suffix}'
            suffix += 1

        user_id = nanoid()
        # No password — Noos-only user. Set a placeholder hash that can never match.
        placeholder_hash = '!noos-oauth'

        db.execute(
            "INSERT INTO user (id, username, display_name, email, password_hash, noos_id) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, noos_name or username, noos_email or None, placeholder_hash, noos_id)
        )
        db.commit()

        # Create git repo for the new user
        try:
            from git_backend import init_user_repo
            init_user_repo(username)
        except Exception:
            pass

        user = User.get(db, user_id)

    login_user(user, remember=True)
    next_page = request.args.get('next')
    return redirect(next_page or url_for('views.dashboard'))


# Ideaflow ID is an additive OIDC relying party. Existing Noos OAuth, local
# passwords, API keys, ListHub user IDs, and local sessions remain independent.
# A link is keyed only by immutable (issuer, subject); email never attaches a
# new subject to an existing account.


def _start_ideaflow_authorization(context):
    client = _ideaflow_client()
    if not client:
        abort(404)
    _prune_ideaflow_contexts()
    try:
        response = client.authorize_redirect(_ideaflow_callback_url())
        state = parse_qs(urlparse(response.headers.get('Location', '')).query).get('state', [''])[0]
        _stash_ideaflow_context(state, context)
    except Exception:
        _prune_ideaflow_contexts()
        flash('Ideaflow sign-in is temporarily unavailable. Please try again.', 'error')
        return redirect(url_for('views.settings') if context['mode'] == 'link' else url_for('auth.login'))
    return response


@auth_bp.route('/auth/ideaflow')
def ideaflow_login():
    return _start_ideaflow_authorization({'mode': 'signin', 'next': _safe_next_url()})


@auth_bp.route('/auth/ideaflow/link')
@_ideaflow_enabled_required
@login_required
def ideaflow_link():
    link_session = session.setdefault(_IDEAFLOW_SESSION_KEY, secrets.token_urlsafe(32))
    return _start_ideaflow_authorization({
        'mode': 'link', 'user_id': current_user.id,
        'auth_session': link_session, 'next': url_for('views.settings'),
    })


@auth_bp.route('/auth/ideaflow/callback')
def ideaflow_callback():
    client = _ideaflow_client()
    if not client:
        abort(404)
    context = _pop_ideaflow_context()
    if not context:
        flash('Ideaflow sign-in could not be verified.', 'error')
        return redirect(url_for('auth.login'))
    try:
        token = client.authorize_access_token(claims_options={
            'iss': {'essential': True, 'value': current_app.config['IDEAFLOW_OIDC_ISSUER']},
            'aud': {'essential': True, 'value': current_app.config['IDEAFLOW_OIDC_CLIENT_ID']},
        })
    except Exception:
        flash('Ideaflow sign-in failed or was cancelled.', 'error')
        return redirect(url_for('auth.login'))
    finally:
        session.pop(_IDEAFLOW_STATE_PREFIX + request.args.get('state', '').strip(), None)

    userinfo = token.get('userinfo') or {}
    issuer = userinfo.get('iss')
    subject = userinfo.get('sub')
    email = (userinfo.get('email') or '').strip().lower() or None
    # OIDC defines this claim as a JSON boolean. Strings such as "true" are
    # untrusted legacy/imported data and must not grant verified-email trust.
    email_verified = userinfo.get('email_verified') is True
    name = (userinfo.get('name') or userinfo.get('preferred_username') or '').strip()
    if not subject or issuer != current_app.config['IDEAFLOW_OIDC_ISSUER']:
        flash('Ideaflow sign-in could not be verified.', 'error')
        return redirect(url_for('auth.login'))

    if context.get('mode') == 'link':
        return _complete_ideaflow_link(context, issuer, subject, email)
    return _complete_ideaflow_signin(context, issuer, subject, email, email_verified, name)


def _find_external_identity(db, issuer, subject):
    return db.execute(
        'SELECT * FROM external_identity WHERE issuer = ? AND subject = ?',
        (issuer, subject),
    ).fetchone()


def _login_external_identity(db, identity, context):
    user = User.get(db, identity['user_id'])
    if not user:
        flash('This Ideaflow identity is linked to an account that no longer exists.', 'error')
        return redirect(url_for('auth.login'))
    login_user(user, remember=True)
    return redirect(_safe_next_url(context.get('next')))


def _unique_oidc_username(db, email, name):
    seed = email.split('@')[0] if email else name
    base = ''.join(c for c in seed.lower() if c.isalnum())[:20]
    if len(base) < 2:
        base = 'user'
    candidate = base
    suffix = 1
    while User.get_by_username(db, candidate):
        candidate = f'{base}{suffix}'
        suffix += 1
    return candidate


def _complete_ideaflow_signin(context, issuer, subject, email, email_verified, name):
    db = get_db()
    identity = _find_external_identity(db, issuer, subject)
    if identity:
        return _login_external_identity(db, identity, context)

    # Even a verified matching email is insufficient to establish identity.
    # Existing users sign in with their current method and explicitly link.
    if email and db.execute(
        'SELECT 1 FROM user WHERE lower(email) = ?', (email,)
    ).fetchone():
        flash(
            'A ListHub account with this email already exists. Sign in to that account, '
            'then link Ideaflow from Settings.',
            'error',
        )
        return redirect(url_for('auth.login'))

    username = _unique_oidc_username(db, email if email_verified else None, name)
    user_id = nanoid()
    trusted_email = email if email_verified else None
    try:
        db.execute('BEGIN')
        db.execute(
            'INSERT INTO user (id, username, display_name, email, password_hash) VALUES (?, ?, ?, ?, ?)',
            (user_id, username, name or username, trusted_email, '!ideaflow-oidc'),
        )
        db.execute(
            'INSERT INTO external_identity (user_id, issuer, subject, email) VALUES (?, ?, ?, ?)',
            (user_id, issuer, subject, email),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        identity = _find_external_identity(db, issuer, subject)
        if identity:
            return _login_external_identity(db, identity, context)
        flash('Ideaflow sign-in conflicted with another request. Please try again.', 'error')
        return redirect(url_for('auth.login'))

    try:
        from git_backend import init_user_repo
        init_user_repo(username)
    except Exception:
        pass
    login_user(User.get(db, user_id), remember=True)
    return redirect(_safe_next_url(context.get('next')))


def _complete_ideaflow_link(context, issuer, subject, email):
    target_user_id = context.get('user_id')
    if (
        not target_user_id or not current_user.is_authenticated or current_user.id != target_user_id
        or not context.get('auth_session')
        or context['auth_session'] != session.get(_IDEAFLOW_SESSION_KEY)
    ):
        flash('Linking must finish in the same signed-in ListHub session that started it.', 'error')
        return redirect(url_for('views.settings') if current_user.is_authenticated else url_for('auth.login'))

    db = get_db()
    identity = _find_external_identity(db, issuer, subject)
    if identity:
        message = (
            'This Ideaflow identity is already linked to your account.'
            if identity['user_id'] == current_user.id
            else 'This Ideaflow identity is already linked to a different account.'
        )
        flash(message, 'error')
        return redirect(url_for('views.settings'))
    if db.execute(
        'SELECT 1 FROM external_identity WHERE user_id = ? AND issuer = ?',
        (current_user.id, issuer),
    ).fetchone():
        flash('Your account is already linked to a different Ideaflow identity.', 'error')
        return redirect(url_for('views.settings'))

    try:
        db.execute(
            'INSERT INTO external_identity (user_id, issuer, subject, email) VALUES (?, ?, ?, ?)',
            (current_user.id, issuer, subject, email),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash('This Ideaflow identity was linked elsewhere. Please try again.', 'error')
        return redirect(url_for('views.settings'))
    flash('Ideaflow identity linked.', 'success')
    return redirect(url_for('views.settings'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        display_name = request.form.get('display_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('register.html')

        if len(username) < 2 or not username.isalnum():
            flash('Username must be at least 2 alphanumeric characters.', 'error')
            return render_template('register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('register.html')

        db = get_db()

        if User.get_by_username(db, username):
            flash('Username already taken.', 'error')
            return render_template('register.html')

        if email and User.get_by_email(db, email):
            flash('Email already registered.', 'error')
            return render_template('register.html')

        user_id = nanoid()
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        db.execute(
            "INSERT INTO user (id, username, display_name, email, password_hash) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, display_name or username, email or None, pw_hash)
        )
        db.commit()

        # Create git repo for the new user
        try:
            from git_backend import init_user_repo
            init_user_repo(username)
        except Exception:
            pass  # Non-fatal if git setup fails

        user = User.get(db, user_id)
        login_user(user, remember=True)
        return redirect(url_for('views.dashboard'))

    return render_template('register.html')
