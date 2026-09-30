from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from common.permissions import user_can_authenticate


class JWTAuthMiddleware:
    """Authenticate websocket clients via JWT query param or Authorization header."""

    def __init__(self, app):
        self.app = app
        self.jwt_authentication = JWTAuthentication()

    async def __call__(self, scope, receive, send):
        token = self._extract_bearer_token(scope)
        scope = dict(scope)
        scope["user"] = await self._get_user(token) if token else AnonymousUser()
        return await self.app(scope, receive, send)

    def _extract_bearer_token(self, scope) -> str | None:
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_token = parse_qs(query_string).get("token", [None])[0]
        if query_token:
            return query_token

        for key, value in scope.get("headers", []):
            if key.lower() != b"authorization":
                continue
            header_value = value.decode("utf-8").strip()
            if not header_value.lower().startswith("bearer "):
                return None
            return header_value.split(" ", 1)[1].strip() or None

        return None

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


def JWTAuthMiddlewareStack(app):
    return JWTAuthMiddleware(app)
