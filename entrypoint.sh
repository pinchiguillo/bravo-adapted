#!/bin/sh
set -e

# Any arguments run instead of the server, e.g. `python manage.py migrate`.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

PORT="${PORT:-8000}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-Core.settings}"

# Migrations run in the one-shot `migrate` compose service, not on every start.
# Daphne's --proxy-headers is deliberately off: it trusts the left-most
# X-Forwarded-For entry, which the client controls. common/client_ip.py
# resolves the client address from TRUSTED_PROXY_IPS instead.
exec daphne -b 0.0.0.0 -p "$PORT" Core.asgi:application
