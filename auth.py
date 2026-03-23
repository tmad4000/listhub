import functools
import hashlib
import os
import secrets
import urllib.parse
import urllib.request
import json

import bcrypt
from flask import Blueprint, request, redirect, url_for, render_template, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from nanoid import generate as nanoid

from db import get_db
from models import User

auth_bp = Blueprint('auth', __name__)

ADMIN_TOKEN = os.environ.get('LISTHUB_ADMIN_TOKEN', '')
NOOS_AUTH_URL = os.environ.get('NOOS_AUTH_URL', 'https://globalbr.ai')  # For browser redirects
NOOS_INTERNAL_URL = os.environ.get('NOOS_INTERNAL_URL', 'http://localhost:4000')  # For server-to-server
NOOS_CLIENT_ID = 'listhub'
LISTHUB_PUBLIC_URL = os.environ.get('LISTHUB_PUBLIC_URL', 'https://listhub.globalbr.ai')


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
