#!/bin/sh
# Prepare the database and static files, then serve the app with Gunicorn behind Nginx.
set -eu
python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 60 \
  --access-logfile - \
  --forwarded-allow-ips "*"
