from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.security.websocket import OriginValidator
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from common.permissions import user_can_authenticate

# Browsers cannot set headers on WebSocket requests, so clients send the token
# as the second subprotocol: new WebSocket(url, ["bearer", accessToken]).
AUTH_SUBPROTOCOL = "bearer"


class JWTAuthMiddleware:
    """Authenticate WebSocket clients with a JWT access token.

    The token is read, in order, from the Sec-WebSocket-Protocol header, the
    Authorization header (non-browser clients) and, only while
    JOB_CHAT_WS_ALLOW_QUERY_TOKEN is on, the ?token= query parameter used by
    the legacy web client (query strings end up in proxy logs).
    """

    def __init__(self, app):
        self.app = app
        self.jwt_authentication = JWTAuthentication()

    async def __call__(self, scope, receive, send):
        token, subprotocol = self._extract_token(scope)
        scope = dict(scope)
        scope["auth_subprotocol"] = subprotocol
        scope["user"] = await self._get_user(token) if token else AnonymousUser()
        return await self.app(scope, receive, send)

    def _extract_token(self, scope):
        subprotocols = scope.get("subprotocols") or []
        if len(subprotocols) >= 2 and subprotocols[0] == AUTH_SUBPROTOCOL:
            return subprotocols[1], AUTH_SUBPROTOCOL

        for key, value in scope.get("headers", []):
            if key.lower() == b"authorization":
                header_value = value.decode("latin1").strip()
                if header_value.lower().startswith("bearer "):
                    return header_value.split(" ", 1)[1].strip() or None, None
                return None, None

        if settings.JOB_CHAT_WS_ALLOW_QUERY_TOKEN:
            query_string = scope.get("query_string", b"").decode("utf-8")
            return parse_qs(query_string).get("token", [None])[0], None
        return None, None

    @database_sync_to_async
    def _get_user(self, token: str):
        try:
            validated_token = self.jwt_authentication.get_validated_token(token)
            user = self.jwt_authentication.get_user(validated_token)
        except (InvalidToken, TokenError, AuthenticationFailed):
            return AnonymousUser()
        # Access tokens outlive a suspension by up to their lifetime; re-check the account.
        if not user_can_authenticate(user):
            return AnonymousUser()
        return user


class BrowserOriginValidator(OriginValidator):
    """Reject browser connections from origins outside WS_ALLOWED_ORIGINS.

    Cross-site WebSocket hijacking needs a victim's browser, and browsers
    always send Origin. Native apps and server-side clients usually do not,
    and they authenticate with a token anyway, so a missing Origin is allowed.
    """

    def valid_origin(self, parsed_origin):
        if parsed_origin is None:
            return True
        return self.validate_origin(parsed_origin)


def JWTAuthMiddlewareStack(app):
    return BrowserOriginValidator(JWTAuthMiddleware(app), settings.WS_ALLOWED_ORIGINS)
