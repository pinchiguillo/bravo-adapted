from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from Core.permissions import IsActiveAccount

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
        summary="Registrar usuario",
        description="Crea una nueva cuenta de usuario y devuelve el perfil registrado.",
    )
    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Iniciar sesion",
        description="Autentica al usuario con email y password y devuelve los tokens JWT de acceso y refresco.",
    )
    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = EmailTokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Refrescar token",
        description="Recibe un refresh token valido y devuelve un nuevo access token JWT.",
    )
    @action(detail=False, methods=["post"], url_path="token/refresh")
    def refresh(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Verificar email",
        description="Valida el token de verificacion y marca el email del usuario como verificado.",
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
        summary="Obtener usuario autenticado",
        description="Devuelve los datos del usuario autenticado a partir del token enviado en la peticion.",
    )
    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        if hasattr(request.user, "Status") and request.user.status != request.user.Status.ACTIVE:
            raise PermissionDenied("User account is not allowed to access this resource.")
        if hasattr(request.user, "email_verified") and not request.user.email_verified:
            raise PermissionDenied("Email is not verified.")
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)
