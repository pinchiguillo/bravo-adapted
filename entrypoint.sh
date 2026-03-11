#!/bin/sh
set -e

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

APP_MODE="${APP_MODE:-development}"
PORT="${PORT:-8000}"

python manage.py migrate

if [ "$APP_MODE" = "production" ]; then
  exec daphne -b 0.0.0.0 -p "$PORT" Core.asgi:application
fi

exec python manage.py runserver 0.0.0.0:"$PORT"
