import os
import secrets

from flask import Flask, render_template, jsonify
from flask_login import LoginManager

from db import init_db, get_db, close_db
from models import User
from auth import auth_bp
from api import api_bp
from views import views_bp
from csrf import generate_csrf_token
from security import add_security_headers


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('LISTHUB_SECRET', secrets.token_hex(32))
    app.config['REMEMBER_COOKIE_DURATION'] = 30 * 24 * 60 * 60  # 30 days
    
    # Session security
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    if os.environ.get('LISTHUB_ENV') == 'production':
        app.config['SESSION_COOKIE_SECURE'] = True

    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        db = get_db()
        return User.get(db, user_id)
    
    # Make CSRF token available in all templates
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf_token)
    
    # Add security headers to all responses
    @app.after_request
    def apply_security_headers(response):
        return add_security_headers(response)
    
    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', error_code=403, error_message='Forbidden'), 403
    
    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', error_code=404, error_message='Page not found'), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        return render_template('error.html', error_code=500, error_message='Internal server error'), 500
    
    # Health check endpoint
    @app.route('/health')
    def health_check():
        from flask import jsonify
        try:
            # Test database connection
            db = get_db()
            db.execute("SELECT 1").fetchone()
            return jsonify({"status": "healthy"}), 200
        except Exception as e:
            return jsonify({"status": "unhealthy", "error": str(e)}), 503

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    # Teardown
    app.teardown_appcontext(close_db)

    # Initialize database
    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3200, debug=True)
