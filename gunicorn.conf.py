# gunicorn.conf.py
# Configuration for Gunicorn WSGI server

# Timeout for worker processes (seconds)
# OpenAI API calls can take a long time for PDF content generation
timeout = 300  # 5 นาที

# Number of worker processes
workers = 1

# Bind address
bind = "0.0.0.0:10000"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Graceful timeout
graceful_timeout = 60

# Keep alive
keepalive = 5
