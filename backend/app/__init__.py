from flask import Flask
import logging
from .k8s_client import init_k8s_client

def create_app():
    """Application Factory Function"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'dev-secret'
    
    # Setup basic logging for the app
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

    # Initialize the Kubernetes client once when the app is created
    init_k8s_client()

    # Register the API blueprint with a URL prefix
    from .api import bp as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    return app
