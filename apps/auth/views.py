from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, Throttled
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenBlacklistSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from common.permissions import IsActiveAccount, get_email_verification_denial_message
from common.throttling import ClientIPScopedRateThrottle

from . import login_guard, sessions
from .serializers import (
    EmailTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)

PUBLIC_ACTIONS = {"register", "login", "refresh", "logout", "verify_email"}


@extend_schema(tags=["Auth"])
class AuthViewSet(viewsets.GenericViewSet):
    queryset = get_user_model().objects.none()
    serializer_class = UserSerializer
    throttle_classes = [ClientIPScopedRateThrottle]

    def get_authenticators(self):
        # Public endpoints ignore the Authorization header, like simplejwt's own
        # views: clients attach their (often expired) access token to every
        # request, which must not break refresh or logout, nor move login
        # attempts out of the per-IP throttle bucket. DRF builds authenticators
        # before self.action exists, hence the route's action map.
        if set(getattr(self, "action_map", {}).values()) <= PUBLIC_ACTIONS:
            return []
        return super().get_authenticators()

    def get_authenticate_header(self, request):
        # Without authenticators DRF would turn 401 responses into 403.
        return 'Bearer realm="api"'

    def get_serializer_class(self):
        if self.action == "register":
            return RegisterSerializer
        if self.action == "login":
            return EmailTokenObtainPairSerializer
        if self.action == "refresh":
            return TokenRefreshSerializer
        if self.action == "logout":
            return TokenBlacklistSerializer
        if self.action == "verify_email":
            return VerifyEmailSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in PUBLIC_ACTIONS:
            return [permissions.AllowAny()]
        return [IsActiveAccount()]

    def get_throttles(self):
        if self.action in PUBLIC_ACTIONS or self.action == "logout_all":
            self.throttle_scope = "auth_logout" if self.action == "logout_all" else f"auth_{self.action}"
            return super().get_throttles()
        return []

    def _build_authenticated_user_response_data(self, user):
        refresh = sessions.issue_tokens(user)
        return {
            **UserSerializer(user, context=self.get_serializer_context()).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

    @extend_schema(
        tags=["Auth"],
        summary="Register user",
        description=(
            "Creates a new user account. When email verification is bypassed, "
            "the response also includes JWT tokens."
        ),
        auth=[],
    )
    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if user.is_email_verified:
            response_data = self._build_authenticated_user_response_data(user)
        else:
            response_data = UserSerializer(
                user, context=self.get_serializer_context()
            ).data
        return Response(response_data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Auth"],
        summary="Login",
        description="Authenticates the user with email and password and returns JWT access and refresh tokens.",
        auth=[],
    )
    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        email = str(request.data.get("email", "")).strip()
        if email and login_guard.is_locked(email):
            raise Throttled(detail="Too many failed login attempts for this account. Try again later.")

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed as exc:
            if email and exc.get_codes() == "no_active_account":
                login_guard.register_failure(email)
            raise
        if email:
            login_guard.reset(email)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Auth"],
        summary="Refresh token",
        description="Receives a valid refresh token and returns a new JWT access token.",
        auth=[],
    )
    @action(detail=False, methods=["post"], url_path="token/refresh")
    def refresh(self, request):
        payload = sessions.verified_payload(str(request.data.get("refresh", "")))
        if payload is not None and sessions.session_expired(payload):
            raise InvalidToken("Session has expired; log in again.")

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            if payload is not None and sessions.is_revoked(payload):
                # A rotated-out refresh token came back: the client or an attacker
                # holds a stolen copy. End every session of the user.
                sessions.revoke_all_refresh_tokens(payload[api_settings.USER_ID_CLAIM])
            raise InvalidToken(exc.args[0]) from exc
        except ObjectDoesNotExist as exc:
            # The token is well-formed but its user has been deleted.
            raise InvalidToken("User not found") from exc
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Auth"],
        summary="Logout",
        description="Revokes the given refresh token. Access tokens expire on their own shortly after.",
        auth=[],
        responses={204: None},
    )
    @action(detail=False, methods=["post"], url_path="logout")
    def logout(self, request):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["Auth"],
        summary="Log out everywhere",
        description="Revokes every refresh token of the authenticated user (all devices).",
        request=None,
        responses={204: None},
    )
    @action(detail=False, methods=["post"], url_path="logout-all")
    def logout_all(self, request):
        sessions.revoke_all_refresh_tokens(request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["Auth"],
        summary="Verify email",
        description="Validates the verification token, marks the user's email as verified and returns JWT tokens.",
        auth=[],
    )
    @action(detail=False, methods=["post"], url_path="verify-email")
    def verify_email(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response_data = self._build_authenticated_user_response_data(user)
        return Response(response_data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Auth"],
        summary="Get authenticated user",
        description="Returns the authenticated user's data based on the token sent in the request.",
    )
    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        if hasattr(request.user, "Status") and request.user.status != request.user.Status.ACTIVE:
            raise PermissionDenied("User account is not allowed to access this resource.")
        email_verification_denial = get_email_verification_denial_message(request.user)
        if email_verification_denial is not None:
            raise PermissionDenied(email_verification_denial)
        serializer = self.get_serializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
