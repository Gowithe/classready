# gunicorn.conf.py
# Configuration for Gunicorn WSGI server

# Timeout for worker processes (seconds)
# OpenAI API calls can take 60-120 seconds for large content generation
timeout = 120

# Number of worker processes
workers = 1

# Bind address
bind = "0.0.0.0:10000"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Graceful timeout
graceful_timeout = 30

# Keep alive
keepalive = 5
