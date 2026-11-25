"""Production Gunicorn configuration for the RevelaCode Flask API."""
import os

# Keep process count conservative by default. Tune only from measured load
# tests and account for one independent MongoClient pool per worker process.
workers = max(1, int(os.getenv("WEB_CONCURRENCY", "2")))
worker_class = "gthread"
threads = max(1, int(os.getenv("GUNICORN_THREADS", "4")))
timeout = max(30, int(os.getenv("GUNICORN_TIMEOUT", "60")))
graceful_timeout = max(10, int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30")))
keepalive = max(1, int(os.getenv("GUNICORN_KEEPALIVE", "5")))
max_requests = max(0, int(os.getenv("GUNICORN_MAX_REQUESTS", "1000")))
max_requests_jitter = max(0, int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100")))
preload_app = False
bind = "0.0.0.0:" + os.getenv("PORT", "5000")
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
