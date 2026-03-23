import os
import uuid
from unittest.mock import patch

import boto3
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMultiAlternatives, get_connection
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from auth.serializers import VerifyEmailSerializer
from auth.views import AuthViewSet
from Core import settings as core_settings


class AwsLocalstackIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s3_enabled = bool(getattr(settings, "USE_S3_STORAGE", False))
        cls.ses_enabled = bool(getattr(settings, "USE_SES_EMAIL", False))
        cls.bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
        cls.sender = getattr(settings, "DEFAULT_FROM_EMAIL", "")

    def setUp(self):
        self.s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_DEFAULT_REGION,
            endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )
        self.ses_client = boto3.client(
            "ses",
            region_name=settings.AWS_DEFAULT_REGION,
            endpoint_url=getattr(settings, "AWS_SES_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )

    def _skip_if_localstack_unavailable(self, callback):
        try:
            callback()
        except (BotoCoreError, ClientError, EndpointConnectionError):
            self.skipTest("Localstack is not reachable from the current test environment.")

    def test_avatar_upload_is_persisted_in_s3(self):
        if not self.s3_enabled:
            self.skipTest("S3 storage is disabled for this environment.")

        self._skip_if_localstack_unavailable(
            lambda: self.s3_client.list_buckets()
        )

        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=f"user_{uuid.uuid4().hex[:8]}",
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            password="test-pass-123",
        )
        avatar = SimpleUploadedFile(
            "avatar.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )
        user.avatar = avatar
        user.save()

        self.assertTrue(user.avatar.name.startswith("avatars/"))
        self.assertTrue(user.avatar.storage.exists(user.avatar.name))

        objects = self.s3_client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=user.avatar.name,
        )
        self.assertGreaterEqual(objects.get("KeyCount", 0), 1)

    def test_ses_email_backend_sends_message(self):
        if not self.ses_enabled:
            self.skipTest("SES email backend is disabled for this environment.")

        try:
            identities = self.ses_client.list_identities(IdentityType="EmailAddress")
        except (BotoCoreError, ClientError, EndpointConnectionError):
            self.skipTest("Localstack is not reachable from the current test environment.")
        self.assertIn(self.sender, identities.get("Identities", []))

        email = EmailMultiAlternatives(
            subject="SES Integration Test",
            body="plain body",
            from_email=self.sender,
            to=["receiver@example.com"],
        )
        email.attach_alternative("<p>html body</p>", "text/html")

        sent_count = get_connection().send_messages([email])
        self.assertEqual(sent_count, 1)


class SettingsEnvHelpersTests(SimpleTestCase):
    def test_env_bool_recognizes_truthy_values(self):
        with patch.dict("os.environ", {"BOOL_FLAG": "true"}, clear=False):
            self.assertTrue(core_settings.env_bool("BOOL_FLAG"))

    def test_env_int_raises_for_invalid_values(self):
        with patch.dict("os.environ", {"INT_FLAG": "invalid"}, clear=False):
            with self.assertRaises(ImproperlyConfigured):
                core_settings.env_int("INT_FLAG", 0)

    def test_env_list_splits_and_strips_values(self):
        with patch.dict("os.environ", {"LIST_FLAG": " a, b ,,c "}, clear=False):
            self.assertEqual(core_settings.env_list("LIST_FLAG"), ["a", "b", "c"])

    def test_require_env_raises_when_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ImproperlyConfigured):
                core_settings.require_env("MISSING_VAR")

    def test_auth_bypass_email_verification_defaults_to_true_in_development(self):
        with patch.dict("os.environ", {"APP_MODE": "development"}, clear=True):
            self.assertTrue(
                core_settings.env_bool(
                    "AUTH_BYPASS_EMAIL_VERIFICATION",
                    default=os.environ.get("APP_MODE", "development").strip().lower() != "production",
                )
            )

    def test_auth_bypass_email_verification_defaults_to_false_in_production(self):
        with patch.dict("os.environ", {"APP_MODE": "production"}, clear=True):
            self.assertFalse(
                core_settings.env_bool(
                    "AUTH_BYPASS_EMAIL_VERIFICATION",
                    default=os.environ.get("APP_MODE", "development").strip().lower() != "production",
                )
            )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUTH_VERIFY_EMAIL_URL_TEMPLATE="https://frontend.example.com/verify-email?token={token}",
    AUTH_BYPASS_EMAIL_VERIFICATION=False,
)
class AuthApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.password = "ChangeMe123!"
        self.email = "root@bravo.example.com"
        self.user = user_model.objects.create_user(
            username="root",
            email=self.email,
            password=self.password,
            email_verified=True,
        )
        mail.outbox = []

    def test_register_sends_verification_email(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "new-user",
                "email": "new-user@example.com",
                "password": "ChangeMe123!",
                "first_name": "New",
                "last_name": "User",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new-user@example.com"])
        self.assertIn("verify-email?token=", mail.outbox[0].body)
        self.assertFalse(response.data["email_verified"])
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["preferencias"], {})
        self.assertEqual(response.data["permissions"], [])

    def test_login_rejects_users_with_unverified_email(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])

        response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Email is not verified.")
        self.assertNotIn("access", response.data)

    def test_login_returns_jwt_tokens_for_email_credentials(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_suspended_users(self):
        self.user.status = self.user.Status.SUSPENDED
        self.user.save(update_fields=["status"])

        response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data["detail"],
            "No active account found with the given credentials",
        )
        self.assertNotIn("access", response.data)

    def test_register_rejects_passwords_blocked_by_django_validators(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "new-user",
                "email": "new-user@example.com",
                "password": "password123",
                "first_name": "New",
                "last_name": "User",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        self.assertFalse(
            get_user_model().objects.filter(email="new-user@example.com").exists()
        )

    def test_refresh_returns_new_access_token(self):
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        refresh_token = login_response.data["refresh"]

        refresh_response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(refresh_response.status_code, 200)
        self.assertIn("access", refresh_response.data)
        self.assertIn("refresh", refresh_response.data)
        self.assertNotEqual(refresh_response.data["refresh"], refresh_token)

    def test_refresh_rejects_invalid_token_with_401(self):
        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": "placeholder"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Token is invalid")
        self.assertEqual(response.data["code"], "token_not_valid")

    def test_me_returns_authenticated_user_profile(self):
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        access_token = login_response.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        me_response = self.client.get("/api/auth/me/")

        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data["email"], self.email)
        self.assertEqual(me_response.data["preferencias"], {})
        self.assertEqual(me_response.data["permissions"], [])

    def test_me_returns_user_permissions_as_strings(self):
        permission = Permission.objects.create(
            codename="can_review_profile",
            name="Can review profile",
            content_type=ContentType.objects.get_for_model(get_user_model()),
        )
        self.user.user_permissions.add(permission)

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["permissions"], ["custom_auth.can_review_profile"])

    def test_me_rejects_suspended_authenticated_user(self):
        self.user.status = self.user.Status.SUSPENDED
        self.user.save(update_fields=["status"])

        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login_response.status_code, 401)

        self.client.force_authenticate(user=self.user)
        me_response = self.client.get("/api/auth/me/")

        self.assertEqual(me_response.status_code, 403)

    def test_token_endpoint_is_not_available(self):
        response = self.client.post(
            "/api/auth/token/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_verify_email_marks_user_as_verified(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])
        token = VerifyEmailSerializer.build_token(self.user)

        response = self.client.post(
            "/api/auth/verify-email/",
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "Email verified successfully.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_verify_email_rejects_invalid_token(self):
        response = self.client.post(
            "/api/auth/verify-email/",
            {"token": "invalid-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["token"][0], "Invalid or expired verification token.")

    def test_verify_email_allows_login_after_successful_verification(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])
        token = VerifyEmailSerializer.build_token(self.user)

        verify_response = self.client.post(
            "/api/auth/verify-email/",
            {"token": token},
            format="json",
        )
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("access", login_response.data)

    def test_verify_email_rejects_expired_token(self):
        token = VerifyEmailSerializer.build_token(self.user)

        with patch("auth.serializers.time.time", return_value=9999999999):
            response = self.client.post(
                "/api/auth/verify-email/",
                {"token": token},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["token"][0], "Invalid or expired verification token.")

    @override_settings(AUTH_BYPASS_EMAIL_VERIFICATION=True)
    def test_register_bypass_marks_user_as_verified_and_skips_email(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "bypass-user",
                "email": "bypass-user@example.com",
                "password": "ChangeMe123!",
                "first_name": "Bypass",
                "last_name": "User",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["email_verified"])
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(AUTH_BYPASS_EMAIL_VERIFICATION=True)
    def test_login_allows_unverified_user_when_bypass_enabled(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])

        response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    @override_settings(AUTH_BYPASS_EMAIL_VERIFICATION=True)
    def test_me_allows_unverified_user_when_bypass_enabled(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.email)


class AuthThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = "ChangeMe123!"
        self.email = "throttle@bravo.example.com"
        self.user = get_user_model().objects.create_user(
            username="throttle-user",
            email=self.email,
            password=self.password,
            email_verified=True,
        )

    def test_login_is_throttled_after_rate_limit(self):
        class LoginTestThrottle(SimpleRateThrottle):
            scope = "auth_login_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        url = "/api/auth/login/"
        payload = {"email": self.email, "password": self.password}
        with patch.object(AuthViewSet, "throttle_classes", [LoginTestThrottle]):
            first_response = self.client.post(url, payload, format="json")
            second_response = self.client.post(url, payload, format="json")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)

    def test_register_is_throttled_after_rate_limit(self):
        class RegisterTestThrottle(SimpleRateThrottle):
            scope = "auth_register_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        url = "/api/auth/register/"
        payload = {
            "username": "new-throttle-user",
            "email": "new-throttle@example.com",
            "password": "ChangeMe123!",
            "first_name": "New",
            "last_name": "User",
        }
        with patch.object(AuthViewSet, "throttle_classes", [RegisterTestThrottle]):
            first_response = self.client.post(url, payload, format="json")
            second_response = self.client.post(url, payload, format="json")

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 429)

    def test_refresh_is_throttled_after_rate_limit(self):
        class RefreshTestThrottle(SimpleRateThrottle):
            scope = "auth_refresh_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        refresh_token = login_response.data["refresh"]
        url = "/api/auth/token/refresh/"
        payload = {"refresh": refresh_token}
        with patch.object(AuthViewSet, "throttle_classes", [RefreshTestThrottle]):
            first_response = self.client.post(url, payload, format="json")
            second_response = self.client.post(url, payload, format="json")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)

    def test_verify_email_is_throttled_after_rate_limit(self):
        class VerifyEmailTestThrottle(SimpleRateThrottle):
            scope = "auth_verify_email_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])
        token = VerifyEmailSerializer.build_token(self.user)
        url = "/api/auth/verify-email/"
        payload = {"token": token}
        with patch.object(AuthViewSet, "throttle_classes", [VerifyEmailTestThrottle]):
            first_response = self.client.post(url, payload, format="json")
            second_response = self.client.post(url, payload, format="json")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)
