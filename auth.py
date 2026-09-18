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
_IDEAFLOW_PENDING_KEY = 'ideaflow_pending_confirm'
_IDEAFLOW_PENDING_TTL = 600
_IDEAFLOW_PENDING_MAX_ATTEMPTS = 5
_IDEAFLOW_FRESH_AUTH_SKEW = 120
_IDEAFLOW_CONFIRM_MAX_FAILURES_PER_USER = 10
_IDEAFLOW_CONFIRM_FAILURE_WINDOW = 600
_ideaflow_confirm_failures = {}
# "Last used" hint: a server-set cookie holding only a method id, written after
# a login handler has established the session (never on click, never on restore).
_LOGIN_HINT_COOKIE = 'listhub_last_login'
_LOGIN_HINT_MAX_AGE = 365 * 24 * 60 * 60


def ideaflow_oidc_enabled(config):
    """Fail closed unless the kill flag and both client credentials exist."""
    return bool(
        config.get('IDEAFLOW_OIDC_ENABLED')
        and config.get('IDEAFLOW_OIDC_CLIENT_ID')
        and config.get('IDEAFLOW_OIDC_CLIENT_SECRET')
    )


def enabled_login_methods(config):
    """Method ids currently offered on the sign-in screens."""
    methods = ['password']
    if NOOS_AUTH_URL:
        methods.append('noos')
    if ideaflow_oidc_enabled(config):
        methods.append('ideaflow')
    return methods


def _remember_login_method(response, method):
    """Record the method of a login that just succeeded on this browser."""
    if method not in enabled_login_methods(current_app.config):
        return response
    try:
        response.set_cookie(
            _LOGIN_HINT_COOKIE, method, max_age=_LOGIN_HINT_MAX_AGE,
            httponly=True, samesite='Lax',
        )
    except Exception:
        pass  # The hint is best-effort; never break a completed login.
    return response


def _login_hint_context():
    """Template context: last successful method, only if 2+ methods are offered."""
    methods = enabled_login_methods(current_app.config)
    stored = request.cookies.get(_LOGIN_HINT_COOKIE)
    return {'last_method': stored if len(methods) > 1 and stored in methods else None}


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
    session.pop(_IDEAFLOW_PENDING_KEY, None)
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
        return render_template('login_choice.html', next_url=_safe_next_url(), **_login_hint_context())
    return redirect(url_for('auth.noos_login'))


@auth_bp.route('/login/local', methods=['GET', 'POST'])
def login_local():
    """Local password login remains available after linking an external identity."""
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
                    return _remember_login_method(
                        redirect(next_page or url_for('views.dashboard')), 'password')
            except Exception:
                pass

        flash('Invalid username or password.', 'error')

    return render_template('login.html', **_login_hint_context())


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
    return _remember_login_method(redirect(next_page or url_for('views.dashboard')), 'noos')


# Ideaflow ID is an additive OIDC relying party. Existing Noos OAuth, local
# passwords, API keys, ListHub user IDs, and local sessions remain independent.
# A link is keyed only by immutable (issuer, subject). Email never attaches a
# new subject to an existing account by itself: ListHub has no email
# verification, so a matching account is confirmed once, in the sign-in flow,
# with its own password (code-d96).


def _start_ideaflow_authorization(context, **authorize_params):
    client = _ideaflow_client()
    if not client:
        abort(404)
    _prune_ideaflow_contexts()
    try:
        response = client.authorize_redirect(_ideaflow_callback_url(), **authorize_params)
        state = parse_qs(urlparse(response.headers.get('Location', '')).query).get('state', [''])[0]
        _stash_ideaflow_context(state, context)
    except Exception:
        _prune_ideaflow_contexts()
        flash('Ideaflow sign-in is temporarily unavailable. Please try again.', 'error')
        return redirect(url_for('views.settings') if context['mode'] == 'link' else url_for('auth.login'))
    return response


@auth_bp.route('/auth/ideaflow')
def ideaflow_login():
    """Fast SSO by default. ``?switch=1`` is the explicit "Use another account"
    action: it sends ``prompt=login`` so the provider shows its sign-in page even
    when an IdP session exists. Only that one allowlisted value is honoured;
    nothing else from the query string is forwarded to the provider."""
    switch = request.args.get('switch') == '1'
    return _start_ideaflow_authorization(
        {'mode': 'signin', 'next': _safe_next_url(), 'switch': switch},
        **({'prompt': 'login'} if switch else {}),
    )


@auth_bp.route('/auth/ideaflow/link')
@_ideaflow_enabled_required
@login_required
def ideaflow_link():
    """Fallback for accounts that could not be resolved at sign-in. A logged-in
    local session alone must never authorize binding whichever person holds the
    IdP session, so this always forces a fresh Ideaflow sign-in (prompt=login)
    and the callback requires a fresh ``auth_time``."""
    link_session = session.setdefault(_IDEAFLOW_SESSION_KEY, secrets.token_urlsafe(32))
    return _start_ideaflow_authorization({
        'mode': 'link', 'user_id': current_user.id,
        'auth_session': link_session, 'next': url_for('views.settings'),
        'started_at': int(time.time()),
    }, prompt='login')


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
    auth_time = userinfo.get('auth_time')
    name = (userinfo.get('name') or userinfo.get('preferred_username') or '').strip()
    if not subject or issuer != current_app.config['IDEAFLOW_OIDC_ISSUER']:
        flash('Ideaflow sign-in could not be verified.', 'error')
        return redirect(url_for('auth.login'))

    if context.get('mode') == 'link':
        return _complete_ideaflow_link(context, issuer, subject, email if email_verified else None, auth_time)
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
    return _remember_login_method(redirect(_safe_next_url(context.get('next'))), 'ideaflow')


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


def _has_usable_password(user):
    """A real bcrypt hash. Placeholders such as '!noos-oauth' and
    '!ideaflow-oidc' mean the account has no local password to check."""
    return bool(user.password_hash) and user.password_hash.startswith('$2')


def _ideaflow_signin_refused(message):
    flash(message, 'error')
    return redirect(url_for('auth.login'))


def _start_ideaflow_ownership_check(user, issuer, subject, email, name, context):
    """`user` is None for reason "choose": the matching account(s) cannot be
    checked with a password (several, none has one, or already connected to
    another Ideaflow identity), and none of them is proven, so the person is
    offered only the way out."""
    session[_IDEAFLOW_PENDING_KEY] = {
        'user_id': user.id if user else None, 'reason': 'password' if user else 'choose',
        'issuer': issuer, 'subject': subject, 'email': email, 'name': name,
        'next': context.get('next'), 'exp': int(time.time()) + _IDEAFLOW_PENDING_TTL,
        'attempts': 0,
    }
    return redirect(url_for('auth.ideaflow_confirm'))


def _load_ideaflow_pending_confirm():
    pending = session.get(_IDEAFLOW_PENDING_KEY)
    required = ('user_id', 'reason', 'issuer', 'subject', 'email', 'exp', 'attempts')
    if (
        not isinstance(pending, dict)
        or any(key not in pending for key in required)
        or not isinstance(pending['exp'], int)
        or pending['exp'] < int(time.time())
    ):
        session.pop(_IDEAFLOW_PENDING_KEY, None)
        return None
    return dict(pending)


def _complete_ideaflow_signin(context, issuer, subject, email, email_verified, name):
    db = get_db()
    # 1. Exact (issuer, subject) is the whole ballgame for a returning person.
    identity = _find_external_identity(db, issuer, subject)
    if identity:
        return _login_external_identity(db, identity, context)

    # 2. A brand new subject whose email matches an existing account. ListHub
    # has NO email-verification flow, so a typed local email proves nothing
    # (its creator may be a squatter who knows the password). Even a strictly
    # verified Ideaflow email is not enough on its own: ownership of the local
    # account is checked once, in the sign-in flow, with that account's own
    # password -- never by email alone and never by forcing a Settings detour.
    if email:
        matches = db.execute('SELECT * FROM user WHERE lower(email) = ?', (email,)).fetchall()
        if matches:
            if not email_verified:
                return _ideaflow_signin_refused(
                    'Ideaflow did not verify this email address, so it can’t be matched to an existing '
                    'ListHub account. Sign in to ListHub another way, then connect Ideaflow from Settings.'
                )
            if len(matches) > 1:
                return _start_ideaflow_ownership_check(None, issuer, subject, email, name, context)
            target = User(matches[0])
            if db.execute(
                'SELECT 1 FROM external_identity WHERE user_id = ? AND issuer = ?',
                (target.id, issuer),
            ).fetchone():
                # May be a squatter who connected their own identity to a row
                # they registered with the victim's address.
                return _start_ideaflow_ownership_check(None, issuer, subject, email, name, context)
            if not _has_usable_password(target):
                return _start_ideaflow_ownership_check(None, issuer, subject, email, name, context)
            return _start_ideaflow_ownership_check(target, issuer, subject, email, name, context)

    # 3. No local account claims this email: a brand new person.
    return _create_ideaflow_account(
        db, context, issuer, subject, email, name,
        local_email=email if email_verified else None,
    )


def _create_ideaflow_account(db, context, issuer, subject, email, name, local_email):
    username = _unique_oidc_username(db, email if local_email else None, name)
    user_id = nanoid()
    try:
        db.execute('BEGIN')
        db.execute(
            'INSERT INTO user (id, username, display_name, email, password_hash) VALUES (?, ?, ?, ?, ?)',
            (user_id, username, name or username, local_email, '!ideaflow-oidc'),
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
    return _remember_login_method(redirect(_safe_next_url(context.get('next'))), 'ideaflow')


@auth_bp.route('/auth/ideaflow/confirm', methods=['GET', 'POST'])
@_ideaflow_enabled_required
def ideaflow_confirm():
    """One-time ownership check. Reached only from the Ideaflow callback when a
    strictly-verified Ideaflow email matches exactly one existing ListHub
    account that has a local password. The person proves they own THAT account
    with its password; only then is the Ideaflow identity bound."""
    pending = _load_ideaflow_pending_confirm()
    if pending is None:
        flash('That Ideaflow confirmation expired. Please continue with Ideaflow again.', 'error')
        return redirect(url_for('auth.login'))
    db = get_db()
    if pending['reason'] == 'choose':
        # No password check is offered; only /auth/ideaflow/confirm/new applies.
        if request.method == 'GET':
            return render_template('ideaflow_confirm.html', reason='choose', username='', email=pending['email'])
        return render_template('ideaflow_confirm.html', reason='choose', username='', email=pending['email']), 400
    user = User.get(db, pending['user_id'])
    if not user or not _has_usable_password(user):
        session.pop(_IDEAFLOW_PENDING_KEY, None)
        flash('That ListHub account can’t be confirmed with a password.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'GET':
        return render_template('ideaflow_confirm.html', reason='password', username=user.username, email=pending['email'])

    # The counter in the session cookie is client-held; this per-account cap is
    # what actually bounds guessing across repeated Ideaflow sign-ins.
    now = time.time()
    failures = _ideaflow_confirm_failures.setdefault(user.id, [])
    failures[:] = [t for t in failures if now - t < _IDEAFLOW_CONFIRM_FAILURE_WINDOW]
    if len(failures) >= _IDEAFLOW_CONFIRM_MAX_FAILURES_PER_USER:
        flash('Too many incorrect attempts for this account. Try again in a few minutes.', 'error')
        return render_template('ideaflow_confirm.html', reason='password', username=user.username, email=pending['email']), 429
    try:
        ok = bcrypt.checkpw(request.form.get('password', '').encode(), user.password_hash.encode())
    except Exception:
        ok = False
    if not ok:
        failures.append(now)
        pending['attempts'] += 1
        if pending['attempts'] >= _IDEAFLOW_PENDING_MAX_ATTEMPTS:
            session.pop(_IDEAFLOW_PENDING_KEY, None)
            flash('Too many incorrect attempts. Please continue with Ideaflow again.', 'error')
            return redirect(url_for('auth.login'))
        session[_IDEAFLOW_PENDING_KEY] = pending
        flash('Incorrect password.', 'error')
        return render_template('ideaflow_confirm.html', reason='password', username=user.username, email=pending['email']), 401

    issuer, subject, email = pending['issuer'], pending['subject'], pending['email']
    context = {'next': pending.get('next')}
    session.pop(_IDEAFLOW_PENDING_KEY, None)

    # Re-check under the proven password; the DB constraints still guard the commit.
    existing = _find_external_identity(db, issuer, subject)
    if existing:
        if existing['user_id'] == user.id:
            return _login_external_identity(db, existing, context)
        return _ideaflow_signin_refused('This Ideaflow account is already connected to a different ListHub account.')
    if db.execute(
        'SELECT 1 FROM external_identity WHERE user_id = ? AND issuer = ?', (user.id, issuer),
    ).fetchone():
        return _ideaflow_signin_refused('That ListHub account is already connected to a different Ideaflow account.')
    try:
        db.execute(
            'INSERT INTO external_identity (user_id, issuer, subject, email) VALUES (?, ?, ?, ?)',
            (user.id, issuer, subject, email),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return _ideaflow_signin_refused('Ideaflow sign-in conflicted with another request. Please try again.')
    flash('Ideaflow is now connected to your ListHub account.', 'success')
    login_user(user, remember=True)
    return redirect(_safe_next_url(context.get('next')))


@auth_bp.route('/auth/ideaflow/confirm/new', methods=['POST'])
@_ideaflow_enabled_required
def ideaflow_confirm_new():
    """"Not your account?" escape hatch. ListHub never verified the matching
    account's email, so the person whose Ideaflow email is provider-verified must
    not be locked out by a squatter, a typo, or a forgotten password. A fresh
    account is created and the existing row is left untouched (its email column
    is UNIQUE, so the new row keeps no email; the identity row keeps it)."""
    pending = _load_ideaflow_pending_confirm()
    session.pop(_IDEAFLOW_PENDING_KEY, None)
    if pending is None:
        flash('That Ideaflow confirmation expired. Please continue with Ideaflow again.', 'error')
        return redirect(url_for('auth.login'))
    db = get_db()
    issuer, subject, email = pending['issuer'], pending['subject'], pending['email']
    context = {'next': pending.get('next')}
    existing = _find_external_identity(db, issuer, subject)
    if existing:
        return _login_external_identity(db, existing, context)
    return _create_ideaflow_account(
        db, context, issuer, subject, email, pending.get('name') or '', local_email=None,
    )


@auth_bp.route('/auth/ideaflow/confirm/cancel', methods=['POST'])
@_ideaflow_enabled_required
def ideaflow_confirm_cancel():
    session.pop(_IDEAFLOW_PENDING_KEY, None)
    return redirect(url_for('auth.login'))


def _complete_ideaflow_link(context, issuer, subject, email, auth_time=None):
    target_user_id = context.get('user_id')
    if (
        not target_user_id or not current_user.is_authenticated or current_user.id != target_user_id
        or not context.get('auth_session')
        or context['auth_session'] != session.get(_IDEAFLOW_SESSION_KEY)
    ):
        flash('Linking must finish in the same signed-in ListHub session that started it.', 'error')
        return redirect(url_for('views.settings') if current_user.is_authenticated else url_for('auth.login'))

    # This flow forced prompt=login, so the provider session must have been
    # (re)created for this request; a stale/missing auth_time means the IdP did
    # not honour it and we would be binding whoever holds the IdP session.
    started_at = context.get('started_at')
    if (
        not isinstance(started_at, int)
        or isinstance(auth_time, bool)
        or not isinstance(auth_time, (int, float))
        or auth_time < started_at - _IDEAFLOW_FRESH_AUTH_SKEW
        or auth_time > int(time.time()) + _IDEAFLOW_FRESH_AUTH_SKEW
    ):
        flash('Ideaflow needs a fresh sign-in to connect an account. Please try connecting again.', 'error')
        return redirect(url_for('views.settings'))

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
        return _remember_login_method(redirect(url_for('views.dashboard')), 'password')

    return render_template('register.html')
