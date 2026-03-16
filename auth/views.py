from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from Core.permissions import IsActiveAccount, get_email_verification_denial_message

from .serializers import (
    EmailTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)


class AuthViewSet(viewsets.GenericViewSet):
    queryset = get_user_model().objects.none()
    serializer_class = UserSerializer
    throttle_classes = [ScopedRateThrottle]

    def get_serializer_class(self):
        if self.action == "register":
            return RegisterSerializer
        if self.action == "login":
            return EmailTokenObtainPairSerializer
        if self.action == "refresh":
            return TokenRefreshSerializer
        if self.action == "verify_email":
            return VerifyEmailSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in {"register", "login", "refresh", "verify_email"}:
            return [permissions.AllowAny()]
        return [IsActiveAccount()]

    def get_throttles(self):
        if self.action in {"register", "login", "refresh", "verify_email"}:
            self.throttle_scope = f"auth_{self.action}"
            return super().get_throttles()
        return []

    @extend_schema(
        summary="Register user",
        description="Creates a new user account and returns the registered profile along with JWT tokens.",
    )
    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        response_data = {
            **UserSerializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Login",
        description="Authenticates the user with email and password and returns JWT access and refresh tokens.",
    )
    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = EmailTokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Refresh token",
        description="Receives a valid refresh token and returns a new JWT access token.",
    )
    @action(detail=False, methods=["post"], url_path="token/refresh")
    def refresh(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Verify email",
        description="Validates the verification token and marks the user's email as verified.",
    )
    @action(detail=False, methods=["post"], url_path="verify-email")
    def verify_email(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Email verified successfully."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
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
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)
