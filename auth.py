import functools
import hashlib
import os

import bcrypt
from flask import Blueprint, request, redirect, url_for, render_template, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from nanoid import generate as nanoid

from db import get_db
from models import User

auth_bp = Blueprint('auth', __name__)

ADMIN_TOKEN = os.environ.get('LISTHUB_ADMIN_TOKEN', '')


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


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        user = User.get_by_username(db, username)

        if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('views.dashboard'))

        flash('Invalid username or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('views.landing'))


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
