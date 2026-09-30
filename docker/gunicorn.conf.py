"""Gunicorn settings for the container.

A single worker process with threads: the JSON store serialises writes with an
in-process lock and the rate limiter is in-memory, so multiple worker processes
would race on read-modify-write of the same files.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
worker_class = "gthread"
timeout = 60            # image uploads are resized synchronously
graceful_timeout = 20
keepalive = 5
max_requests = 2000     # recycle periodically to keep memory flat
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
forwarded_allow_ips = "*"   # only the reverse proxy can reach the container
