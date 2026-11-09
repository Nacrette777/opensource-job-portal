#!/bin/sh
# Optional start-up steps, opt-in so that several replicas do not race:
# run migrations from one place (a one-off job, or a single replica).
set -e
if [ "${DJANGO_MIGRATE_ON_START:-0}" = "1" ]; then
    python manage.py migrate --noinput
fi
exec "$@"
