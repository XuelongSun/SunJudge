"""Single-process deployment: the grading queue is process-local."""
bind = "127.0.0.1:8000"
workers = 1
worker_class = "gthread"
threads = 8
preload_app = False
timeout = 120
graceful_timeout = 120
# Do not recycle the worker while its in-memory grading queue has work.
max_requests = 0
accesslog = "-"
errorlog = "-"
capture_output = True
