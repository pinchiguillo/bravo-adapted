from unittest.mock import patch
from unittest import SkipTest

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework.throttling import ScopedRateThrottle

RGPD_INSTALLED = django_apps.is_installed("apps.rgpd")

if RGPD_INSTALLED:
    from .models import (
        RgpdAnonymousConsent,
        RgpdAnonymousConsentEvent,
        RgpdConsent,
        RgpdConsentEvent,
    )
    from .views import RgpdAnonymousConsentViewSet
else:
    raise SkipTest("rgpd app disabled")


class RgpdConsentApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="rgpd-user",
            email="rgpd-user@example.com",
            password="testpass123",
        )
        self.url = reverse("rgpd-me")

    def test_me_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_default_consent_state_for_authenticated_user_without_sensitive_metadata(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["cookies_accepted"], False)
        self.assertEqual(response.data["privacy_policy_accepted"], False)
        self.assertEqual(response.data["terms_and_conditions_accepted"], False)
        self.assertIsNone(response.data["cookies_accepted_at"])
        self.assertIsNone(response.data["privacy_policy_accepted_at"])
        self.assertIsNone(response.data["terms_and_conditions_accepted_at"])
        self.assertNotIn("ip_address", response.data)
        self.assertNotIn("user_agent", response.data)

    def test_me_rejects_suspended_user(self):
        self.user.status = self.user.Status.SUSPENDED
        self.user.save(update_fields=["status"])
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_me_creates_consent_and_history_event(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {
                "cookies_accepted": True,
                "cookies_version": "2026-03",
                "privacy_policy_accepted": True,
                "privacy_policy_version": "v3",
                "terms_and_conditions_accepted": True,
                "terms_and_conditions_version": "v7",
                "source": "web-register",
            },
            format="json",
            HTTP_USER_AGENT="BravoApp/1.0",
            REMOTE_ADDR="203.0.113.10",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("ip_address", response.data)
        self.assertNotIn("user_agent", response.data)

        consent = RgpdConsent.objects.get(user=self.user)
        self.assertTrue(consent.cookies_accepted)
        self.assertTrue(consent.privacy_policy_accepted)
        self.assertTrue(consent.terms_and_conditions_accepted)
        self.assertEqual(consent.cookies_version, "2026-03")
        self.assertEqual(consent.privacy_policy_version, "v3")
        self.assertEqual(consent.terms_and_conditions_version, "v7")
        self.assertEqual(consent.source, "web-register")
        self.assertEqual(consent.ip_address, "203.0.113.10")
        self.assertEqual(consent.user_agent, "BravoApp/1.0")
        self.assertIsNotNone(consent.cookies_accepted_at)
        self.assertIsNotNone(consent.privacy_policy_accepted_at)
        self.assertIsNotNone(consent.terms_and_conditions_accepted_at)

        event = RgpdConsentEvent.objects.get(consent=consent)
        self.assertEqual(event.action, "upsert")
        self.assertEqual(event.ip_address, "203.0.113.10")
        self.assertEqual(event.user_agent, "BravoApp/1.0")
        self.assertTrue(event.cookies_accepted)

    @override_settings(TRUSTED_PROXY_IPS=["198.51.100.1"])
    def test_post_me_ignores_forwarded_for_when_request_does_not_come_from_trusted_proxy(self):
        self.client.force_authenticate(user=self.user)

        self.client.post(
            self.url,
            {
                "cookies_accepted": True,
            },
            format="json",
            HTTP_X_FORWARDED_FOR="192.0.2.44, 198.51.100.1",
            REMOTE_ADDR="203.0.113.55",
        )

        consent = RgpdConsent.objects.get(user=self.user)
        self.assertEqual(consent.ip_address, "203.0.113.55")

    def test_patch_me_updates_existing_consent_state_and_appends_history(self):
        consent = RgpdConsent.objects.create(
            user=self.user,
            cookies_accepted=True,
            cookies_version="2026-03",
            privacy_policy_accepted=True,
            privacy_policy_version="v3",
            terms_and_conditions_accepted=True,
            terms_and_conditions_version="v7",
            source="web-register",
            ip_address="203.0.113.10",
            user_agent="BravoApp/1.0",
        )
        RgpdConsentEvent.objects.create(
            consent=consent,
            action="upsert",
            cookies_accepted=True,
            cookies_accepted_at=consent.cookies_accepted_at,
            cookies_version="2026-03",
            privacy_policy_accepted=True,
            privacy_policy_accepted_at=consent.privacy_policy_accepted_at,
            privacy_policy_version="v3",
            terms_and_conditions_accepted=True,
            terms_and_conditions_accepted_at=consent.terms_and_conditions_accepted_at,
            terms_and_conditions_version="v7",
            source="web-register",
            ip_address="203.0.113.10",
            user_agent="BravoApp/1.0",
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            self.url,
            {
                "cookies_accepted": False,
                "cookies_version": "",
                "source": "settings-panel",
            },
            format="json",
            HTTP_USER_AGENT="BravoApp/1.1",
            REMOTE_ADDR="198.51.100.5",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("ip_address", response.data)
        self.assertNotIn("user_agent", response.data)

        consent.refresh_from_db()
        self.assertFalse(consent.cookies_accepted)
        self.assertIsNone(consent.cookies_accepted_at)
        self.assertEqual(consent.cookies_version, "")
        self.assertTrue(consent.privacy_policy_accepted)
        self.assertEqual(consent.source, "settings-panel")
        self.assertEqual(consent.ip_address, "198.51.100.5")
        self.assertEqual(consent.user_agent, "BravoApp/1.1")
        self.assertEqual(RgpdConsentEvent.objects.filter(consent=consent).count(), 2)


class RgpdAnonymousConsentApiTests(APITestCase):
    def setUp(self):
        self.url = reverse("rgpd-anonymous-list")

    def test_public_anonymous_endpoint_creates_consent_with_server_generated_credentials(self):
        response = self.client.post(
            self.url,
            {
                "cookies_accepted": True,
                "cookies_version": "2026-03",
                "privacy_policy_accepted": True,
                "privacy_policy_version": "v3",
                "terms_and_conditions_accepted": False,
                "terms_and_conditions_version": "",
                "source": "cookie-banner",
            },
            format="json",
            HTTP_USER_AGENT="BravoLanding/1.0",
            REMOTE_ADDR="203.0.113.20",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("identifier", response.data)
        self.assertIn("write_token", response.data)
        self.assertNotIn("ip_address", response.data)
        self.assertNotIn("user_agent", response.data)

        consent = RgpdAnonymousConsent.objects.get(identifier=response.data["identifier"])
        self.assertTrue(consent.cookies_accepted)
        self.assertTrue(consent.privacy_policy_accepted)
        self.assertFalse(consent.terms_and_conditions_accepted)
        self.assertEqual(consent.ip_address, "203.0.113.20")
        self.assertEqual(consent.user_agent, "BravoLanding/1.0")

        event = RgpdAnonymousConsentEvent.objects.get(consent=consent)
        self.assertEqual(event.action, "create")
        self.assertEqual(event.ip_address, "203.0.113.20")

    def test_public_anonymous_endpoint_requires_write_token_for_updates(self):
        create_response = self.client.post(
            self.url,
            {
                "cookies_accepted": True,
                "source": "cookie-banner",
            },
            format="json",
        )
        identifier = create_response.data["identifier"]

        response = self.client.post(
            self.url,
            {
                "identifier": identifier,
                "cookies_accepted": False,
                "source": "checkout",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["non_field_errors"], ["identifier and write_token must be provided together."])

    def test_public_anonymous_endpoint_rejects_updates_with_invalid_write_token_without_disclosing_existence(self):
        create_response = self.client.post(
            self.url,
            {
                "cookies_accepted": True,
                "source": "cookie-banner",
            },
            format="json",
        )
        identifier = create_response.data["identifier"]

        response = self.client.post(
            self.url,
            {
                "identifier": identifier,
                "write_token": "invalid-token",
                "cookies_accepted": False,
                "source": "checkout",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Anonymous consent not found.")

    def test_public_anonymous_endpoint_updates_existing_identifier_when_write_token_matches(self):
        create_response = self.client.post(
            self.url,
            {
                "cookies_accepted": True,
                "cookies_version": "2026-03",
                "source": "cookie-banner",
            },
            format="json",
            HTTP_USER_AGENT="BravoLanding/1.0",
            REMOTE_ADDR="203.0.113.20",
        )

        response = self.client.post(
            self.url,
            {
                "identifier": create_response.data["identifier"],
                "write_token": create_response.data["write_token"],
                "cookies_accepted": False,
                "cookies_version": "",
                "terms_and_conditions_accepted": True,
                "terms_and_conditions_version": "v7",
                "source": "checkout",
            },
            format="json",
            HTTP_USER_AGENT="BravoLanding/1.1",
            REMOTE_ADDR="198.51.100.9",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("write_token", response.data)
        consent = RgpdAnonymousConsent.objects.get(identifier=create_response.data["identifier"])
        self.assertFalse(consent.cookies_accepted)
        self.assertTrue(consent.terms_and_conditions_accepted)
        self.assertEqual(consent.terms_and_conditions_version, "v7")
        self.assertEqual(consent.source, "checkout")
        self.assertEqual(consent.ip_address, "198.51.100.9")
        self.assertEqual(consent.user_agent, "BravoLanding/1.1")
        self.assertEqual(RgpdAnonymousConsentEvent.objects.filter(consent=consent).count(), 2)

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "rgpd-throttle-tests",
            }
        },
    )
    def test_public_anonymous_endpoint_is_throttled(self):
        cache.clear()
        factory = APIRequestFactory()
        view = RgpdAnonymousConsentViewSet()
        view.action = "create"
        view.action_map = {"post": "create"}
        throttle_rates = {
            "rgpd_authenticated_read": "10/minute",
            "rgpd_authenticated_write": "10/minute",
            "rgpd_anonymous_write": "2/minute",
        }

        with patch.object(ScopedRateThrottle, "THROTTLE_RATES", throttle_rates):
            allowed_results = []
            for _ in range(3):
                raw_request = factory.post(self.url, {"cookies_accepted": True}, format="json")
                request = view.initialize_request(raw_request)
                view.request = request
                throttle = view.get_throttles()[0]
                allowed_results.append(throttle.allow_request(request, view))

        self.assertEqual(allowed_results, [True, True, False])
