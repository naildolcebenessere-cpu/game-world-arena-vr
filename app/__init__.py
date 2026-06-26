from datetime import timedelta
from flask import Flask
from .db import init_db, seed_if_empty, close_db
from .routes import bp
import os


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cambia-questa-chiave-segreta')
    app.config['DATABASE_URL'] = os.environ.get('DATABASE_URL', '').strip()
    app.config['DATABASE'] = os.environ.get('SQLITE_PATH') or os.path.join(app.instance_path, 'arena.sqlite')
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_MB', '12')) * 1024 * 1024

    # Sicurezza sessione per uso online.
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    app.permanent_session_lifetime = timedelta(hours=int(os.environ.get('SESSION_HOURS', '8')))

    os.makedirs(app.instance_path, exist_ok=True)
    app.register_blueprint(bp)
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()
        seed_if_empty()
    return app
