from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.auth.services import build_verify_email_token
from apps.auth.views import AuthViewSet
from apps.organization.models import Organization


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
        self.email = "root@example.com"
        self.user = user_model.objects.create_user(
            username="root",
            email=self.email,
            password=self.password,
            email_verified=True,
        )
        mail.outbox = []

    def build_register_payload(self, **overrides):
        payload = {
            "username": "new-user",
            "email": "new-user@example.com",
            "password": "ChangeMe123!",
            "first_name": "New",
            "last_name": "User",
            "rgpd": {
                "privacy_policy_accepted": True,
                "terms_and_conditions_accepted": True,
                "cookies_accepted": False,
                "source": "auth-tests",
            },
        }
        payload.update(overrides)
        return payload

    def test_register_sends_verification_email(self):
        response = self.client.post(
            "/api/auth/register/",
            self.build_register_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new-user@example.com"])
        self.assertIn("verify-email?token=", mail.outbox[0].body)
        self.assertFalse(response.data["email_verified"])
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertNotIn("id", response.data)
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
            self.build_register_payload(password="password123"),
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

    def _login_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_rotated_refresh_token_cannot_be_reused(self):
        old_refresh = self._login_tokens()["refresh"]

        first = self.client.post("/api/auth/token/refresh/", {"refresh": old_refresh}, format="json")
        replay = self.client.post("/api/auth/token/refresh/", {"refresh": old_refresh}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.data["code"], "token_not_valid")

    def test_logout_revokes_the_refresh_token(self):
        refresh = self._login_tokens()["refresh"]

        logout = self.client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
        reuse = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")

        self.assertEqual(logout.status_code, 204)
        self.assertEqual(reuse.status_code, 401)

    def test_logout_rejects_invalid_token_with_401(self):
        response = self.client.post("/api/auth/logout/", {"refresh": "placeholder"}, format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "token_not_valid")

    def test_suspended_user_cannot_refresh(self):
        refresh = self._login_tokens()["refresh"]
        self.user.status = self.user.Status.SUSPENDED
        self.user.save(update_fields=["status"])

        response = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "No active account found for the given token.")

    def test_refresh_for_deleted_user_returns_401(self):
        refresh = self._login_tokens()["refresh"]
        self.user.delete()

        response = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "token_not_valid")

    def test_access_tokens_are_short_lived(self):
        from datetime import timedelta

        from rest_framework_simplejwt.settings import api_settings

        self.assertLessEqual(api_settings.ACCESS_TOKEN_LIFETIME, timedelta(minutes=15))
        self.assertTrue(api_settings.ROTATE_REFRESH_TOKENS)
        self.assertTrue(api_settings.BLACKLIST_AFTER_ROTATION)

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
        self.assertFalse(me_response.data["is_provider"])
        self.assertIsNone(me_response.data["provider_uuid"])
        self.assertEqual(me_response.data["permissions"], [])
        self.assertNotIn("id", me_response.data)

    def test_me_returns_provider_uuid_for_provider_user(self):
        organization = Organization.objects.create(
            user=self.user,
            name="Provider Org",
            legal_name="Provider Org SL",
            tax_id="B12345678",
            billing_email="billing@provider.test",
            billing_address="Main street 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_provider"])
        self.assertEqual(response.data["provider_uuid"], str(organization.uuid))
        self.assertNotIn("id", response.data)

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
        token = build_verify_email_token(self.user)

        response = self.client.post(
            "/api/auth/verify-email/",
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.email)
        self.assertTrue(response.data["email_verified"])
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("id", response.data)
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

    def test_verify_email_rejects_reused_token(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])
        token = build_verify_email_token(self.user)

        first_response = self.client.post(
            "/api/auth/verify-email/",
            {"token": token},
            format="json",
        )
        second_response = self.client.post(
            "/api/auth/verify-email/",
            {"token": token},
            format="json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(
            second_response.data["token"][0],
            "Invalid or expired verification token.",
        )

    def test_verify_email_allows_login_after_successful_verification(self):
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])
        token = build_verify_email_token(self.user)

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
        self.assertIn("access", verify_response.data)
        self.assertIn("refresh", verify_response.data)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("access", login_response.data)

    def test_verify_email_rejects_expired_token(self):
        token = build_verify_email_token(self.user)

        with patch("apps.auth.services.time.time", return_value=9999999999):
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
            self.build_register_payload(
                username="bypass-user",
                email="bypass-user@example.com",
                first_name="Bypass",
                last_name="User",
                rgpd={
                    "privacy_policy_accepted": True,
                    "terms_and_conditions_accepted": True,
                    "cookies_accepted": False,
                    "source": "auth-bypass-tests",
                },
            ),
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

    @override_settings(AUTH_BYPASS_EMAIL_VERIFICATION=True)
    def test_user_model_exposes_bypass_as_verified_state(self):
        self.user.email_verified = False

        self.assertTrue(self.user.is_email_verified)


class AuthThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = "ChangeMe123!"
        self.email = "throttle@example.com"
        self.user = get_user_model().objects.create_user(
            username="throttle-user",
            email=self.email,
            password=self.password,
            email_verified=True,
        )

    def build_register_payload(self, **overrides):
        payload = {
            "username": "new-throttle-user",
            "email": "new-throttle@example.com",
            "password": "ChangeMe123!",
            "first_name": "New",
            "last_name": "User",
            "rgpd": {
                "privacy_policy_accepted": True,
                "terms_and_conditions_accepted": True,
                "cookies_accepted": False,
                "source": "auth-throttle-tests",
            },
        }
        payload.update(overrides)
        return payload

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
        payload = self.build_register_payload()
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

    @override_settings(AUTH_BYPASS_EMAIL_VERIFICATION=False)
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
        token = build_verify_email_token(self.user)
        url = "/api/auth/verify-email/"
        payload = {"token": token}
        with patch.object(AuthViewSet, "throttle_classes", [VerifyEmailTestThrottle]):
            first_response = self.client.post(url, payload, format="json")
            second_response = self.client.post(url, payload, format="json")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)
