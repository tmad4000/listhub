"""Security utilities and middleware"""
from flask import Response


def add_security_headers(response):
    """Add security headers to response."""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Prevent MIME sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # XSS protection (legacy browsers)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content Security Policy
    # Note: 'unsafe-inline' is used for compatibility with existing inline scripts/styles
    # For production, consider refactoring to use nonces or external files
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'"
    )
    
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    return response


def validate_item_input(title, content, slug):
    """Validate item input fields.
    
    Returns (is_valid, error_message) tuple.
    """
    if title and len(title) > 500:
        return False, "Title must be 500 characters or less"
    
    if content and len(content) > 1_000_000:  # 1MB limit
        return False, "Content must be 1MB or less"
    
    if slug and len(slug) > 200:
        return False, "Slug must be 200 characters or less"
    
    return True, None


def validate_username(username):
    """Validate username format.
    
    Returns (is_valid, error_message) tuple.
    """
    if not username:
        return False, "Username is required"
    
    if len(username) < 2:
        return False, "Username must be at least 2 characters"
    
    if len(username) > 39:
        return False, "Username must be 39 characters or less"
    
    if not username.isalnum():
        return False, "Username must be alphanumeric"
    
    return True, None


def validate_password(password):
    """Validate password strength.
    
    Returns (is_valid, error_message) tuple.
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if len(password) > 72:  # bcrypt limit
        return False, "Password must be 72 characters or less"
    
    return True, None
