#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && \
   [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && \
   [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    python manage.py createsuperuser --no-input || echo "Superuser creation skipped or failed; check deployment logs."
fi