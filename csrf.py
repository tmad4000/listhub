"""CSRF protection for forms"""
import secrets
import hmac
import hashlib
from functools import wraps
from flask import session, request, abort


def generate_csrf_token():
    """Generate a CSRF token and store it in the session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf_token(token):
    """Validate the provided CSRF token against the session token."""
    session_token = session.get('_csrf_token')
    if not session_token or not token:
        return False
    return hmac.compare_digest(session_token, token)


def csrf_protect(f):
    """Decorator to protect routes with CSRF validation."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not validate_csrf_token(token):
                abort(403, description="CSRF token validation failed")
        return f(*args, **kwargs)
    return decorated_function
