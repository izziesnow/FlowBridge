#!/bin/sh
# Start-up for a hosted test copy on Render (render.yaml). There is no Nginx here: Render
# terminates HTTPS, WhiteNoise serves static files and the app adds the security headers.
set -eu
python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0
python manage.py prepare_hosted_data
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 60 \
  --access-logfile - \
  --forwarded-allow-ips "*"
