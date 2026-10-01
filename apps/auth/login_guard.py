"""Per-account limit on failed logins.

The IP-based throttle stops one client hammering the API; this stops many
clients (a botnet, or one client rotating IPv6 addresses) guessing the
password of one account. Counters live in the shared cache, keyed by a hash
of the normalised email.
"""

from django.conf import settings
from django.core.cache import cache
from django.utils.crypto import salted_hmac


def _key(email):
    digest = salted_hmac("auth.login-failures", email.strip().lower()).hexdigest()
    return f"auth:login-failures:{digest}"


def is_locked(email):
    return (cache.get(_key(email)) or 0) >= settings.AUTH_LOGIN_MAX_FAILURES


def register_failure(email):
    key = _key(email)
    if cache.add(key, 1, timeout=settings.AUTH_LOGIN_FAILURE_WINDOW_SECONDS):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=settings.AUTH_LOGIN_FAILURE_WINDOW_SECONDS)


def reset(email):
    cache.delete(_key(email))
