import logging

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .permissions import user_has_jobs_access

logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app
        self.jwt_auth = JWTAuthentication()

    async def __call__(self, scope, receive, send):
        raw_token = self._extract_bearer_token(scope)

        user = AnonymousUser()
        if raw_token:
            try:
                validated_token = self.jwt_auth.get_validated_token(raw_token)
                user = await self._get_user(validated_token)
                if not user_has_jobs_access(user):
                    user = AnonymousUser()
            except (InvalidToken, TokenError, AuthenticationFailed, ValueError) as exc:
                logger.warning(
                    "ws_jwt_auth_failed",
                    extra={
                        "reason": exc.__class__.__name__,
                        "path": scope.get("path", ""),
                        "token_source": "authorization_header",
                    },
                )
                user = AnonymousUser()

        scope["user"] = user
        return await self.app(scope, receive, send)

    def _extract_bearer_token(self, scope):
        headers = scope.get("headers", [])
        for header_name, header_value in headers:
            if header_name.lower() != b"authorization":
                continue

            auth_value = header_value.decode("utf-8", errors="ignore").strip()
            auth_parts = auth_value.split(" ", 1)
            if len(auth_parts) != 2 or auth_parts[0].lower() != "bearer":
                return None

            token = auth_parts[1].strip()
            return token or None
        return None

    @database_sync_to_async
    def _get_user(self, validated_token):
        return self.jwt_auth.get_user(validated_token)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
