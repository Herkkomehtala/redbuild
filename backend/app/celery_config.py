import os

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
broker_url = REDIS_URL
result_backend = REDIS_URL
broker_connection_retry_on_startup = True
