from app import create_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app

app = create_app()

# --- METRICS INTEGRATION ---
metrics_app = make_wsgi_app()

app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
    '/metrics': metrics_app
})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
