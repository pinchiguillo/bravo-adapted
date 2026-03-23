import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from Core.permissions import get_email_verification_denial_message

VERIFY_EMAIL_SALT = "auth.verify_email"
VERIFY_EMAIL_MAX_AGE_SECONDS = 60 * 60 * 24


def build_verify_email_url(token):
    return settings.AUTH_VERIFY_EMAIL_URL_TEMPLATE.format(token=token)


def send_verification_email(user):
    token = VerifyEmailSerializer.build_token(user)
    verification_url = build_verify_email_url(token)
    subject = "Verify your email"
    message = (
        "Welcome to Bravo.\n\n"
        "Verify your email by opening this link:\n"
        f"{verification_url}\n"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


class UserSerializer(serializers.ModelSerializer):
    preferencias = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "uuid",
            "username",
            "email",
            "email_verified",
            "first_name",
            "last_name",
            "status",
            "preferencias",
            "permissions",
        )

    @extend_schema_field({"type": "object", "additionalProperties": {}})
    def get_preferencias(self, obj):
        return {}

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj):
        return sorted(obj.get_all_permissions())


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8 if settings.AUTH_ENFORCE_PASSWORD_RESTRICTIONS else None,
    )

    class Meta:
        model = get_user_model()
        fields = ("username", "email", "password", "first_name", "last_name")

    def validate(self, attrs):
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
                raise serializers.ValidationError({"password": exc.messages})
        return attrs

    def create(self, validated_data):
        user_model = get_user_model()
        with transaction.atomic():
            user = user_model.objects.create_user(**validated_data)
            if settings.AUTH_BYPASS_EMAIL_VERIFICATION:
                user.email_verified = True
                user.save(update_fields=["email_verified"])
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
            payload = signing.loads(value, salt=VERIFY_EMAIL_SALT)
            expires_at = payload["exp"]
            if expires_at < time.time():
                raise signing.SignatureExpired("Token expired.")
            user = user_model.objects.get(pk=payload["user_id"])
        except (KeyError, signing.BadSignature, signing.SignatureExpired, user_model.DoesNotExist):
            raise serializers.ValidationError(self.error_messages["invalid_token"])

        self.context["user"] = user
        return value

    def save(self, **kwargs):
        user = self.context["user"]
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
        return user

    @classmethod
    def build_token(cls, user):
        return signing.dumps(
            {
                "user_id": user.pk,
                "exp": int(time.time()) + VERIFY_EMAIL_MAX_AGE_SECONDS,
            },
            salt=VERIFY_EMAIL_SALT,
        )
