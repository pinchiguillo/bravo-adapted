#!/bin/sh
set -e

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

APP_MODE="${APP_MODE:-development}"
PORT="${PORT:-8000}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-Core.settings}"

python manage.py migrate

exec daphne -b 0.0.0.0 -p "$PORT" Core.asgi:application
