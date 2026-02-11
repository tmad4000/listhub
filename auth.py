import functools
import hashlib

import bcrypt
from flask import Blueprint, request, redirect, url_for, render_template, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from nanoid import generate as nanoid

from db import get_db
from models import User
from csrf import csrf_protect
from security import validate_username, validate_password

auth_bp = Blueprint('auth', __name__)


def hash_api_key(raw_key):
    """Hash an API key with SHA-256 for fast lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def require_api_auth(f):
    """Decorator: authenticate via Bearer token or session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated:
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            raw_key = auth_header[7:]
            key_h = hash_api_key(raw_key)
            db = get_db()
            user = User.get_by_api_key(db, key_h)
            if user:
                # Attach scopes from the key
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
@csrf_protect
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
@csrf_protect
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        display_name = request.form.get('display_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Validate username
        is_valid, error = validate_username(username)
        if not is_valid:
            flash(error, 'error')
            return render_template('register.html')

        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            flash(error, 'error')
            return render_template('register.html')
        
        # Validate display name length
        if display_name and len(display_name) > 100:
            flash('Display name must be 100 characters or less.', 'error')
            return render_template('register.html')
        
        # Validate email length
        if email and len(email) > 255:
            flash('Email must be 255 characters or less.', 'error')
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

        user = User.get(db, user_id)
        login_user(user, remember=True)
        return redirect(url_for('views.dashboard'))

    return render_template('register.html')
