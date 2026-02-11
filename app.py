import os
import secrets

from flask import Flask
from flask_login import LoginManager

from db import init_db, get_db, close_db
from models import User
from auth import auth_bp
from api import api_bp
from views import views_bp
from git_backend import git_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('LISTHUB_SECRET', secrets.token_hex(32))
    app.config['REMEMBER_COOKIE_DURATION'] = 30 * 24 * 60 * 60  # 30 days

    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        db = get_db()
        return User.get(db, user_id)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(git_bp)

    # Teardown
    app.teardown_appcontext(close_db)

    # Initialize database
    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3200, debug=True)
