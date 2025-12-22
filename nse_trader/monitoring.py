from prometheus_client import start_http_server, Counter
from .app import app
from prometheus_client import REGISTRY, generate_latest

API_REQUESTS = Counter('api_requests', 'Total API requests', ['endpoint', 'status'])
VALIDATION_ERRORS = Counter('validation_errors', 'Data validation issues', ['symbol', 'type'])

@app.route('/metrics')
def metrics():
    return generate_latest(REGISTRY)
