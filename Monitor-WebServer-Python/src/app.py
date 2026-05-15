import os
from flask import Flask
from database import get_db
from auth import init_default_user
from routes.api import api_bp
from routes.views import views_bp
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Register Blueprints
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Initialize database indexes and default user
    with app.app_context():
        try:
            init_default_user()
            
            from pymongo import DESCENDING
            db = get_db()
            db.create_index([('time', DESCENDING)], background=True)
            db.create_index([('ip', 1)], background=True)
            db.create_index([('is_attack', 1)], background=True)
            print("✓ App initialization complete")
        except Exception as e:
            print(f"Warning during app initialization: {e}")
            
    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG)
