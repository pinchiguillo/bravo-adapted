from unittest import SkipTest
from unittest.mock import patch

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
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
        RgpdDataRequest,
        RgpdLegalDocument,
        RgpdPolicyAcceptance,
        RgpdPolicyDocument,
    )
    from .services import get_current_policy_versions
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
        self.current_versions = get_current_policy_versions()

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
        self.assertEqual(
            consent.cookies_version,
            self.current_versions[RgpdPolicyDocument.DocumentType.COOKIES_POLICY].version,
        )
        self.assertEqual(
            consent.privacy_policy_version,
            self.current_versions[RgpdPolicyDocument.DocumentType.PRIVACY_POLICY].version,
        )
        self.assertEqual(
            consent.terms_and_conditions_version,
            self.current_versions[RgpdPolicyDocument.DocumentType.TERMS_AND_CONDITIONS].version,
        )
        self.assertEqual(consent.source, "web-register")
        self.assertEqual(consent.ip_address, "203.0.113.10")
        self.assertEqual(consent.user_agent, "BravoApp/1.0")
        self.assertIsNotNone(consent.cookies_accepted_at)
        self.assertIsNotNone(consent.privacy_policy_accepted_at)
        self.assertIsNotNone(consent.terms_and_conditions_accepted_at)
        self.assertEqual(
            RgpdPolicyAcceptance.objects.filter(
                user=self.user,
                policy_version=self.current_versions[
                    RgpdPolicyDocument.DocumentType.PRIVACY_POLICY
                ],
            ).count(),
            1,
        )

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
        self.assertTrue(response.data["requires_reacceptance"])


class RgpdAnonymousConsentApiTests(APITestCase):
    def setUp(self):
        self.url = reverse("rgpd-anonymous-list")
        self.current_versions = get_current_policy_versions()

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


class RgpdLegalDocumentApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="legal-doc-user",
            email="legal-doc-user@example.com",
            password="testpass123",
        )
        self.other_user = user_model.objects.create_user(
            username="legal-doc-other",
            email="legal-doc-other@example.com",
            password="testpass123",
        )
        self.url = reverse("rgpd-legal-documents-list")

    def test_legal_document_list_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_legal_document_upload_uses_separate_bucket_and_user_scoped_prefix(self):
        self.client.force_authenticate(user=self.user)
        storage = RgpdLegalDocument._meta.get_field("file").storage

        with patch.object(storage, "_save", side_effect=lambda name, content: name) as save_mock:
            response = self.client.post(
                self.url,
                {
                    "document_type": "privacy-policy",
                    "file": SimpleUploadedFile(
                        "privacy-policy.pdf",
                        b"%PDF-1.4 legal document",
                        content_type="application/pdf",
                    ),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(storage.bucket_name, "bravo-media-legal")
        document = RgpdLegalDocument.objects.get(user=self.user)
        self.assertEqual(document.document_type, "privacy-policy")
        self.assertEqual(document.original_name, "privacy-policy.pdf")
        self.assertEqual(document.content_type, "application/pdf")
        self.assertEqual(document.size_bytes, len(b"%PDF-1.4 legal document"))
        self.assertTrue(
            document.file.name.startswith(
                f"{settings.LEGAL_DOCUMENTS_UPLOAD_PREFIX}/users/{self.user.uuid}/"
            )
        )
        save_mock.assert_called_once()

    def test_legal_document_list_is_scoped_to_authenticated_user(self):
        storage = RgpdLegalDocument._meta.get_field("file").storage
        with patch.object(storage, "_save", side_effect=lambda name, content: name):
            RgpdLegalDocument.objects.create(
                user=self.user,
                document_type="privacy-policy",
                file=SimpleUploadedFile(
                    "user.pdf",
                    b"%PDF-1.4 user",
                    content_type="application/pdf",
                ),
                original_name="user.pdf",
                content_type="application/pdf",
                size_bytes=len(b"%PDF-1.4 user"),
            )
            RgpdLegalDocument.objects.create(
                user=self.other_user,
                document_type="terms",
                file=SimpleUploadedFile(
                    "other.pdf",
                    b"%PDF-1.4 other",
                    content_type="application/pdf",
                ),
                original_name="other.pdf",
                content_type="application/pdf",
                size_bytes=len(b"%PDF-1.4 other"),
            )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["document_type"], "privacy-policy")
        self.assertEqual(response.data["results"][0]["original_name"], "user.pdf")

    @override_settings(
        LEGAL_DOCUMENT_ALLOWED_CONTENT_TYPES=["application/pdf"],
        LEGAL_DOCUMENT_MAX_BYTES=8,
    )
    def test_legal_document_upload_validates_type_and_size(self):
        self.client.force_authenticate(user=self.user)

        invalid_type_response = self.client.post(
            self.url,
            {
                "document_type": "privacy-policy",
                "file": SimpleUploadedFile(
                    "privacy-policy.txt",
                    b"plain-text",
                    content_type="text/plain",
                ),
            },
            format="multipart",
        )
        oversized_response = self.client.post(
            self.url,
            {
                "document_type": "privacy-policy",
                "file": SimpleUploadedFile(
                    "privacy-policy.pdf",
                    b"123456789",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )

        self.assertEqual(invalid_type_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            invalid_type_response.data["file"][0],
            "Unsupported legal document content type.",
        )
        self.assertEqual(oversized_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            oversized_response.data["file"][0],
            "Legal document exceeds maximum allowed size.",
        )


class RgpdAnonymousConsentBehaviorTests(APITestCase):
    def setUp(self):
        self.url = reverse("rgpd-anonymous-list")
        self.current_versions = get_current_policy_versions()

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
        self.assertEqual(
            consent.terms_and_conditions_version,
            self.current_versions[
                RgpdPolicyDocument.DocumentType.TERMS_AND_CONDITIONS
            ].version,
        )
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


class RgpdPublicDocumentsApiTests(APITestCase):
    def test_active_documents_endpoint_returns_current_published_versions(self):
        response = self.client.get(reverse("rgpd-documents-active"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(
            {item["type"] for item in response.data},
            {
                RgpdPolicyDocument.DocumentType.PRIVACY_POLICY,
                RgpdPolicyDocument.DocumentType.TERMS_AND_CONDITIONS,
                RgpdPolicyDocument.DocumentType.COOKIES_POLICY,
            },
        )


class RgpdDataRequestApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="rgpd-request-user",
            email="rgpd-request-user@example.com",
            password="testpass123",
        )
        self.url = reverse("rgpd-requests-me")

    def test_authenticated_user_can_create_and_list_data_requests(self):
        self.client.force_authenticate(user=self.user)

        create_response = self.client.post(
            self.url,
            {
                "request_type": "portability",
                "details": "Exportad mis datos de cuenta y actividad.",
            },
            format="json",
        )
        list_response = self.client.get(self.url)

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["status"], "submitted")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["request_type"], "portability")


class RgpdRegisterIntegrationTests(APITestCase):
    def test_register_requires_rgpd_payload_when_module_is_enabled(self):
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

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rgpd", response.data)

    def test_register_creates_user_and_rgpd_acceptances(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "rgpd-register",
                "email": "rgpd-register@example.com",
                "password": "ChangeMe123!",
                "first_name": "Rgpd",
                "last_name": "Register",
                "rgpd": {
                    "privacy_policy_accepted": True,
                    "terms_and_conditions_accepted": True,
                    "cookies_accepted": False,
                    "source": "web-signup",
                },
            },
            format="json",
            HTTP_USER_AGENT="BravoWeb/1.0",
            REMOTE_ADDR="203.0.113.7",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(email="rgpd-register@example.com")
        consent = RgpdConsent.objects.get(user=user)
        self.assertTrue(consent.privacy_policy_accepted)
        self.assertTrue(consent.terms_and_conditions_accepted)
        self.assertFalse(consent.cookies_accepted)
        self.assertEqual(consent.source, "web-signup")
        self.assertEqual(
            RgpdPolicyAcceptance.objects.filter(
                user=user,
                policy_version__document__document_type=RgpdPolicyDocument.DocumentType.PRIVACY_POLICY,
            ).count(),
            1,
        )


class ManagementRgpdApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="rgpd-admin",
            email="rgpd-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.user = user_model.objects.create_user(
            username="rgpd-managed-user",
            email="rgpd-managed-user@example.com",
            password="testpass123",
        )
        self.data_request = RgpdDataRequest.objects.create(
            user=self.user,
            request_type=RgpdDataRequest.RequestType.ACCESS,
            details="Necesito copia de mis datos.",
        )

    def test_admin_can_list_documents_and_publish_new_version(self):
        self.client.force_authenticate(user=self.admin_user)
        create_response = self.client.post(
            reverse("management-rgpd-document-versions-list"),
            {
                "document_type": RgpdPolicyDocument.DocumentType.PRIVACY_POLICY,
                "version": "2026-06",
                "title": "Politica de privacidad junio 2026",
                "body_markdown": "Nuevo texto legal.",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        publish_response = self.client.post(
            reverse(
                "management-rgpd-document-versions-publish",
                kwargs={"uuid": create_response.data["uuid"]},
            )
        )
        documents_response = self.client.get(reverse("management-rgpd-documents-list"))

        self.assertEqual(publish_response.status_code, status.HTTP_200_OK)
        self.assertEqual(documents_response.status_code, status.HTTP_200_OK)
        privacy_document = next(
            item
            for item in documents_response.data["results"]
            if item["document_type"] == RgpdPolicyDocument.DocumentType.PRIVACY_POLICY
        )
        self.assertEqual(privacy_document["current_version"]["version"], "2026-06")

    def test_admin_can_resolve_rgpd_data_request(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.patch(
            reverse(
                "management-rgpd-requests-detail",
                kwargs={"uuid": self.data_request.uuid},
            ),
            {
                "status": "completed",
                "resolution_notes": "Exportacion enviada por canal seguro.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.data_request.refresh_from_db()
        self.assertEqual(self.data_request.status, RgpdDataRequest.Status.COMPLETED)
        self.assertEqual(
            self.data_request.resolution_notes,
            "Exportacion enviada por canal seguro.",
        )
        self.assertEqual(self.data_request.resolved_by, self.admin_user)
