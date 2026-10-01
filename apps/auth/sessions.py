"""JWT session lifecycle: issuing, expiry, reuse detection and revocation.

A session starts at login. Its refresh token rotates on every use, and the
auth_time claim travels with it, so a session cannot be extended beyond
JWT_MAX_SESSION_AGE by refreshing forever.
"""

import time

from django.conf import settings
from rest_framework_simplejwt.exceptions import TokenBackendError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

AUTH_TIME_CLAIM = "auth_time"


def issue_tokens(user):
    """Start a new session for the user and return its refresh token."""
    refresh = RefreshToken.for_user(user)
    refresh[AUTH_TIME_CLAIM] = int(time.time())
    return refresh


def verified_payload(raw_token):
    """Payload of a correctly signed, unexpired token, or None. Ignores the blacklist."""
    try:
        return token_backend.decode(raw_token, verify=True)
    except TokenBackendError:
        return None


def session_expired(payload):
    auth_time = payload.get(AUTH_TIME_CLAIM)
    if auth_time is None:
        return False
    return time.time() - auth_time > settings.JWT_MAX_SESSION_AGE.total_seconds()


def is_revoked(payload):
    return BlacklistedToken.objects.filter(token__jti=payload.get(api_settings.JTI_CLAIM)).exists()


def revoke_all_refresh_tokens(user_id):
    """Blacklist every outstanding refresh token of a user; returns how many were revoked."""
    outstanding = OutstandingToken.objects.filter(user_id=user_id, blacklistedtoken__isnull=True)
    revoked = [BlacklistedToken(token=token) for token in outstanding]
    BlacklistedToken.objects.bulk_create(revoked, ignore_conflicts=True)
    return len(revoked)
