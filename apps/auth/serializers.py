from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from common.client_ip import get_client_ip
from common.permissions import get_email_verification_denial_message

from .services import load_verify_email_user_id, send_verification_email

if django_apps.is_installed("apps.rgpd"):
    from apps.rgpd.serializers import RegisterRgpdSerializer
    from apps.rgpd.services import create_user_rgpd_consent


class UserSerializer(serializers.ModelSerializer):
    preferencias = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    is_provider = serializers.SerializerMethodField()
    provider_uuid = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = (
            "uuid",
            "username",
            "email",
            "email_verified",
            "first_name",
            "last_name",
            "status",
            "preferencias",
            "permissions",
            "is_provider",
            "provider_uuid",
        )

    @extend_schema_field({"type": "object", "additionalProperties": {}})
    def get_preferencias(self, obj):
        return {}

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj):
        return sorted(obj.get_all_permissions())

    @extend_schema_field(serializers.BooleanField())
    def get_is_provider(self, obj):
        return self._get_provider(obj) is not None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_provider_uuid(self, obj):
        provider = self._get_provider(obj)
        if provider is None:
            return None
        return str(provider.uuid)

    def _get_provider(self, obj):
        provider = getattr(obj, "_auth_provider_cache", None)
        if provider is not None:
            return provider

        try:
            provider = obj.organization
        except ObjectDoesNotExist:
            provider = None

        obj._auth_provider_cache = provider
        return provider


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8 if settings.AUTH_ENFORCE_PASSWORD_RESTRICTIONS else None,
    )
    if django_apps.is_installed("apps.rgpd"):
        rgpd = RegisterRgpdSerializer()

    class Meta:
        model = get_user_model()
        fields = ("username", "email", "password", "first_name", "last_name") + (
            ("rgpd",) if django_apps.is_installed("apps.rgpd") else ()
        )

    def validate(self, attrs):
        rgpd_required = django_apps.is_installed("apps.rgpd") and settings.RGPD_MODULE_ENABLED
        if rgpd_required and "rgpd" not in attrs:
            raise serializers.ValidationError({"rgpd": ["This field is required."]})

        user = get_user_model()(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        if settings.AUTH_ENFORCE_PASSWORD_RESTRICTIONS:
            try:
                validate_password(attrs["password"], user=user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        user_model = get_user_model()
        rgpd_data = validated_data.pop("rgpd", None)
        with transaction.atomic():
            user = user_model.objects.create_user(**validated_data)
            if rgpd_data is not None and django_apps.is_installed("apps.rgpd") and settings.RGPD_MODULE_ENABLED:
                request = self.context.get("request")
                create_user_rgpd_consent(
                    user=user,
                    consent_data=rgpd_data,
                    ip_address=get_client_ip(request) if request is not None else None,
                    user_agent=request.META.get("HTTP_USER_AGENT", "") if request is not None else "",
                )
            if user.is_email_verified:
                user.mark_email_verified()
            else:
                send_verification_email(user)
        return user


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = get_user_model().USERNAME_FIELD

    def validate(self, attrs):
        data = super().validate(attrs)
        email_verification_denial = get_email_verification_denial_message(self.user)
        if email_verification_denial is not None:
            raise AuthenticationFailed(email_verification_denial)
        if self.user.status != self.user.Status.ACTIVE:
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                code="no_active_account",
            )
        return data


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField()

    default_error_messages = {
        "invalid_token": "Invalid or expired verification token.",
    }

    def validate_token(self, value):
        user_model = get_user_model()

        try:
            user_id = load_verify_email_user_id(value)
            user = user_model.objects.get(pk=user_id)
            if user.is_email_verified:
                raise serializers.ValidationError(self.error_messages["invalid_token"])
        except (KeyError, signing.BadSignature, signing.SignatureExpired, user_model.DoesNotExist):
            raise serializers.ValidationError(self.error_messages["invalid_token"]) from None

        self.context["user"] = user
        return value

    def save(self, **kwargs):
        user = self.context["user"]
        user.mark_email_verified()
        return user
