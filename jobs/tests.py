from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken

from organization.models import Organization, Service, ServicePrice

from .models import Job, JobChatAttachment, JobChatMessage
from .routing import websocket_urlpatterns
from .views import JobViewSet
from .ws_auth import JWTAuthMiddleware, JWTAuthMiddlewareStack


class JobAttachmentDownloadUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.job = object()

    @override_settings(JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS=120)
    def test_returns_presigned_url_with_ttl_when_storage_supports_expire(self):
        storage = SimpleNamespace()
        storage.url = lambda name, expire=None: "https://files.example.com/presigned"
        attachment = SimpleNamespace(
            file=SimpleNamespace(
                name="job-chat-attachments/2026/03/11/proof.txt",
                storage=storage,
            ),
        )

        request = self.factory.get("/api/jobs/job/messages/1/attachments/2/download/")
        view = JobViewSet()
        view.request = request
        view.get_object = lambda: self.job

        with patch("jobs.views.JobChatAttachment.objects.select_related") as select_related_mock:
            queryset = select_related_mock.return_value
            queryset.filter.return_value.first.return_value = attachment
            response = view.download_attachment(request, uuid="job", message_id="1", attachment_id="2")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["download_url"], "https://files.example.com/presigned")
        self.assertEqual(response.data["expires_in"], 120)
        self.assertEqual(response.data["filename"], "proof.txt")

    @override_settings(JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS=120)
    def test_falls_back_to_url_without_expire_when_storage_does_not_accept_it(self):
        def storage_url_without_expire(file_name):
            return f"/media/{file_name}"

        storage = SimpleNamespace(url=storage_url_without_expire)
        attachment = SimpleNamespace(
            file=SimpleNamespace(
                name="job-chat-attachments/2026/03/11/proof.txt",
                storage=storage,
            ),
        )

        request = self.factory.get("/api/jobs/job/messages/1/attachments/2/download/")
        view = JobViewSet()
        view.request = request
        view.get_object = lambda: self.job

        with patch("jobs.views.JobChatAttachment.objects.select_related") as select_related_mock:
            queryset = select_related_mock.return_value
            queryset.filter.return_value.first.return_value = attachment
            response = view.download_attachment(request, uuid="job", message_id="1", attachment_id="2")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["download_url"].startswith("http://testserver/media/"))
        self.assertEqual(response.data["expires_in"], 120)
        self.assertEqual(response.data["filename"], "proof.txt")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    MEDIA_ROOT="/tmp/bravo-job-tests-media",
    MEDIA_URL="/media/",
)
class JobsApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client_user = user_model.objects.create_user(
            username="client",
            email="client@example.com",
            password="testpass123",
            email_verified=True,
        )
        self.organization_owner = user_model.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
            email_verified=True,
        )
        self.admin_user = user_model.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="testpass123",
            is_staff=True,
            email_verified=True,
        )

        self.organization = Organization.objects.create(
            user=self.organization_owner,
            name="Acme",
            legal_name="Acme SL",
            tax_id="A123",
            billing_email="billing@acme.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
        )
        self.service = Service.objects.create(organization=self.organization, name="Plan", description="")
        self.service_price = ServicePrice.objects.create(
            service=self.service,
            amount="99.99",
            currency="EUR",
            effective_from=date(2026, 1, 1),
        )
        self.second_organization = Organization.objects.create(
            user=self.client_user,
            name="Client Org",
            legal_name="Client Org SL",
            tax_id="C789",
            billing_email="billing@clientorg.com",
            billing_address="Third 3",
            billing_city="Valencia",
            billing_country="ES",
            billing_postal_code="46001",
        )
        self.second_service = Service.objects.create(
            organization=self.second_organization,
            name="Second Plan",
            description="",
        )
        self.second_service_price = ServicePrice.objects.create(
            service=self.second_service,
            amount="49.99",
            currency="EUR",
            effective_from=date(2026, 1, 1),
        )

    def test_create_job_creates_chat(self):
        self.client.force_authenticate(user=self.client_user)

        response = self.client.post(
            reverse("jobs-list"),
            {
                "organization": self.organization.id,
                "plan_price": self.service_price.id,
                "status": Job.Status.PENDING,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        job = Job.objects.get(id=response.data["id"])
        self.assertTrue(hasattr(job, "chat"))

    def test_create_job_rejects_non_pending_status(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("jobs-list"),
            {
                "organization": self.organization.id,
                "plan_price": self.service_price.id,
                "status": Job.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_job_member_cannot_change_status_directly(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.patch(
            reverse("jobs-detail", kwargs={"uuid": job.uuid}),
            {"status": Job.Status.ACTIVE},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.PENDING)

    def test_job_member_cannot_change_organization_or_plan_price(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.patch(
            reverse("jobs-detail", kwargs={"uuid": job.uuid}),
            {
                "organization": self.second_organization.id,
                "plan_price": self.second_service_price.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("organization", response.data)
        self.assertIn("plan_price", response.data)
        job.refresh_from_db()
        self.assertEqual(job.organization_id, self.organization.id)
        self.assertEqual(job.plan_price_id, self.service_price.id)

    def test_non_member_cannot_partial_update_job(self):
        outsider = get_user_model().objects.create_user(
            username="jobs-update-outsider",
            email="jobs-update-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=outsider)
        response = self.client.patch(
            reverse("jobs-detail", kwargs={"uuid": job.uuid}),
            {"status": Job.Status.ACTIVE},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.PENDING)

    def test_non_admin_cannot_delete_job(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.delete(reverse("jobs-detail", kwargs={"uuid": job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Job.objects.filter(uuid=job.uuid).exists())

    def test_admin_can_delete_job(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(reverse("jobs-detail", kwargs={"uuid": job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Job.objects.filter(uuid=job.uuid).exists())

    def test_job_messages_requires_job_membership(self):
        outsider = get_user_model().objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
            email_verified=True,
        )
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=outsider)
        response = self.client.get(reverse("jobs-messages", kwargs={"uuid": job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_job_list_is_scoped_to_member_jobs(self):
        owner_job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        outsider = get_user_model().objects.create_user(
            username="jobs-outsider",
            email="jobs-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )
        outsider_org = Organization.objects.create(
            user=outsider,
            name="Outsider Org",
            legal_name="Outsider Org SL",
            tax_id="D100",
            billing_email="billing@outsider.com",
            billing_address="Fourth 4",
            billing_city="Sevilla",
            billing_country="ES",
            billing_postal_code="41001",
        )
        outsider_service = Service.objects.create(organization=outsider_org, name="Out Plan", description="")
        outsider_price = ServicePrice.objects.create(
            service=outsider_service,
            amount="10.00",
            currency="EUR",
            effective_from=date(2026, 1, 1),
        )
        outsider_job = Job.objects.create(
            user=outsider,
            organization=outsider_org,
            plan_price=outsider_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(reverse("jobs-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_job_ids = {item["id"] for item in response.data}
        self.assertIn(owner_job.id, returned_job_ids)
        self.assertNotIn(outsider_job.id, returned_job_ids)

    def test_create_job_rejects_plan_price_from_another_organization(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("jobs-list"),
            {
                "organization": self.organization.id,
                "plan_price": self.second_service_price.id,
                "status": Job.Status.PENDING,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_price", response.data)

    def test_create_job_message_rejects_blank_content(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("jobs-messages", kwargs={"uuid": job.uuid}),
            {"content": "   "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content", response.data)

    def test_upload_attachment_requires_job_membership(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        outsider = get_user_model().objects.create_user(
            username="attachment-outsider",
            email="attachment-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )

        self.client.force_authenticate(user=outsider)
        response = self.client.post(
            reverse("jobs-attachments", kwargs={"uuid": job.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(JobChatAttachment.objects.count(), 0)

    def test_upload_attachment_returns_404_when_message_not_found(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("jobs-attachments", kwargs={"uuid": job.uuid, "message_id": 999999}),
            {"file": SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_attachment_succeeds_for_job_member(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("jobs-attachments", kwargs={"uuid": job.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(JobChatAttachment.objects.count(), 1)
        self.assertIn("download_url", response.data)
        self.assertIn("filename", response.data)
        self.assertNotIn("file", response.data)

    def test_upload_attachment_requires_message_sender(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")

        self.client.force_authenticate(user=self.organization_owner)
        response = self.client.post(
            reverse("jobs-attachments", kwargs={"uuid": job.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(JobChatAttachment.objects.count(), 0)

    @override_settings(
        JOB_CHAT_ATTACHMENT_ALLOWED_CONTENT_TYPES=("text/plain",),
        JOB_CHAT_ATTACHMENT_MAX_BYTES=4,
    )
    def test_upload_attachment_rejects_invalid_type_and_oversize(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        self.client.force_authenticate(user=self.client_user)

        invalid_type_response = self.client.post(
            reverse("jobs-attachments", kwargs={"uuid": job.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.pdf", b"abcd", content_type="application/pdf")},
            format="multipart",
        )
        oversize_response = self.client.post(
            reverse("jobs-attachments", kwargs={"uuid": job.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.txt", b"abcde", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(invalid_type_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", invalid_type_response.data)
        self.assertEqual(oversize_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", oversize_response.data)
        self.assertEqual(JobChatAttachment.objects.count(), 0)

    def test_upload_attachment_rejects_mismatched_file_signature(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        self.client.force_authenticate(user=self.client_user)

        response = self.client.post(
            reverse("jobs-attachments", kwargs={"uuid": job.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.pdf", b"plain text payload", content_type="application/pdf")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)
        self.assertEqual(JobChatAttachment.objects.count(), 0)

    def test_job_detail_returns_404_for_non_member(self):
        outsider = get_user_model().objects.create_user(
            username="jobs-detail-outsider",
            email="jobs-detail-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=outsider)
        response = self.client.get(reverse("jobs-detail", kwargs={"uuid": job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unverified_user_cannot_access_jobs_api(self):
        unverified_user = get_user_model().objects.create_user(
            username="jobs-unverified",
            email="jobs-unverified@example.com",
            password="testpass123",
            email_verified=False,
        )

        self.client.force_authenticate(user=unverified_user)
        response = self.client.get(reverse("jobs-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Email is not verified.")

    def test_download_attachment_requires_job_access(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        attachment = JobChatAttachment.objects.create(
            message=message,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain"),
        )
        outsider = get_user_model().objects.create_user(
            username="jobs-download-outsider",
            email="jobs-download-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )

        self.client.force_authenticate(user=outsider)
        response = self.client.get(
            reverse(
                "jobs-download-attachment",
                kwargs={"uuid": job.uuid, "message_id": message.id, "attachment_id": attachment.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_attachment_returns_file_for_job_member(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        attachment = JobChatAttachment.objects.create(
            message=message,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain"),
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(
            reverse(
                "jobs-download-attachment",
                kwargs={"uuid": job.uuid, "message_id": message.id, "attachment_id": attachment.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("download_url", response.data)
        self.assertIn("expires_in", response.data)
        self.assertIn("filename", response.data)
        self.assertIn("proof", response.data["filename"])
        self.assertTrue(response.data["download_url"].startswith("http://testserver/"))

    @override_settings(JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS=123)
    def test_download_attachment_uses_ttl_when_storage_supports_expire(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        attachment = JobChatAttachment.objects.create(
            message=message,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain"),
        )

        self.client.force_authenticate(user=self.client_user)
        with patch.object(
            JobChatAttachment._meta.get_field("file").storage,
            "url",
            return_value="https://files.example.com/presigned",
        ) as url_mock:
            response = self.client.get(
                reverse(
                    "jobs-download-attachment",
                    kwargs={"uuid": job.uuid, "message_id": message.id, "attachment_id": attachment.id},
                )
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["download_url"], "https://files.example.com/presigned")
        self.assertEqual(response.data["expires_in"], 123)
        url_mock.assert_called_once_with(attachment.file.name, expire=123)

    @override_settings(JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS=123)
    def test_download_attachment_falls_back_when_storage_has_no_expire_kwarg(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        attachment = JobChatAttachment.objects.create(
            message=message,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain"),
        )

        self.client.force_authenticate(user=self.client_user)

        def storage_url_without_expire(file_name):
            return f"/media/{file_name}"

        with patch.object(
            JobChatAttachment._meta.get_field("file").storage,
            "url",
            side_effect=storage_url_without_expire,
        ) as url_mock:
            response = self.client.get(
                reverse(
                    "jobs-download-attachment",
                    kwargs={"uuid": job.uuid, "message_id": message.id, "attachment_id": attachment.id},
                )
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["download_url"].startswith("http://testserver/media/"))
        self.assertEqual(response.data["expires_in"], 123)
        self.assertEqual(url_mock.call_count, 2)

    def test_job_list_is_throttled(self):
        cache.clear()
        self.client.force_authenticate(user=self.client_user)

        class JobsReadTestThrottle(SimpleRateThrottle):
            scope = "jobs_read_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        with patch.object(JobViewSet, "throttle_classes", [JobsReadTestThrottle]):
            first_response = self.client.get(reverse("jobs-list"))
            second_response = self.client.get(reverse("jobs-list"))

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_create_job_is_throttled(self):
        cache.clear()
        self.client.force_authenticate(user=self.client_user)
        payload = {
            "organization": self.organization.id,
            "plan_price": self.service_price.id,
            "status": Job.Status.PENDING,
        }

        class JobsWriteTestThrottle(SimpleRateThrottle):
            scope = "jobs_write_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        with patch.object(JobViewSet, "throttle_classes", [JobsWriteTestThrottle]):
            first_response = self.client.post(reverse("jobs-list"), payload, format="json")
            second_response = self.client.post(reverse("jobs-list"), payload, format="json")

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_create_job_message_is_throttled(self):
        job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=self.service_price,
            status=Job.Status.PENDING,
        )
        self.client.force_authenticate(user=self.client_user)

        class JobsMessagesTestThrottle(SimpleRateThrottle):
            scope = "jobs_messages_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        with patch.object(JobViewSet, "throttle_classes", [JobsMessagesTestThrottle]):
            first_response = self.client.post(
                reverse("jobs-messages", kwargs={"uuid": job.uuid}),
                {"content": "first"},
                format="json",
            )
            second_response = self.client.post(
                reverse("jobs-messages", kwargs={"uuid": job.uuid}),
                {"content": "second"},
                format="json",
            )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class JwtAuthMiddlewareTests(APITestCase):
    def _run_middleware(self, middleware, scope):
        resolved = {}

        async def app(received_scope, receive, send):
            resolved["user"] = received_scope.get("user")
            return None

        async def fake_receive():
            return {"type": "websocket.connect"}

        async def fake_send(message):
            return None

        middleware.app = app
        async_to_sync(middleware)(scope, fake_receive, fake_send)
        return resolved["user"]

    def test_assigns_user_when_token_is_valid(self):
        user = get_user_model().objects.create_user(
            username="ws-user",
            email="ws-user@example.com",
            password="testpass123",
            email_verified=True,
        )
        middleware = JWTAuthMiddleware(app=None)

        with (
            patch.object(middleware.jwt_auth, "get_validated_token", return_value="validated"),
            patch.object(middleware, "_get_user", return_value=user),
        ):
            resolved_user = self._run_middleware(
                middleware,
                {
                    "type": "websocket",
                    "path": "/ws/jobs/",
                    "headers": [(b"authorization", b"Bearer valid-token")],
                    "query_string": b"",
                },
            )

        self.assertEqual(resolved_user, user)

    def test_assigns_anonymous_and_logs_when_token_is_invalid(self):
        middleware = JWTAuthMiddleware(app=None)

        with (
            patch.object(middleware.jwt_auth, "get_validated_token", side_effect=InvalidToken("bad token")),
            patch("jobs.ws_auth.logger.warning") as warning_mock,
        ):
            resolved_user = self._run_middleware(
                middleware,
                {
                    "type": "websocket",
                    "path": "/ws/jobs/",
                    "headers": [(b"authorization", b"Bearer secret-token")],
                    "query_string": b"",
                },
            )

        self.assertTrue(resolved_user.is_anonymous)

        warning_mock.assert_called_once()
        warning_extra = warning_mock.call_args.kwargs.get("extra", {})
        self.assertEqual(warning_mock.call_args.args[0], "ws_jwt_auth_failed")
        self.assertEqual(warning_extra.get("reason"), "InvalidToken")
        self.assertEqual(warning_extra.get("path"), "/ws/jobs/")
        self.assertEqual(warning_extra.get("token_source"), "authorization_header")
        self.assertNotIn("secret-token", str(warning_mock.call_args))

    def test_assigns_anonymous_when_token_is_missing(self):
        middleware = JWTAuthMiddleware(app=None)
        resolved_user = self._run_middleware(
            middleware,
            {"type": "websocket", "path": "/ws/jobs/", "headers": [], "query_string": b""},
        )

        self.assertTrue(resolved_user.is_anonymous)

    def test_ignores_query_string_token_when_authorization_header_is_missing(self):
        middleware = JWTAuthMiddleware(app=None)
        with patch.object(middleware.jwt_auth, "get_validated_token") as validate_token_mock:
            resolved_user = self._run_middleware(
                middleware,
                {
                    "type": "websocket",
                    "path": "/ws/jobs/",
                    "headers": [],
                    "query_string": b"token=legacy-token",
                },
            )

        self.assertTrue(resolved_user.is_anonymous)
        validate_token_mock.assert_not_called()

    def test_assigns_anonymous_for_malformed_authorization_header(self):
        middleware = JWTAuthMiddleware(app=None)
        with patch.object(middleware.jwt_auth, "get_validated_token") as validate_token_mock:
            resolved_user = self._run_middleware(
                middleware,
                {
                    "type": "websocket",
                    "path": "/ws/jobs/",
                    "headers": [(b"authorization", b"Token malformed")],
                    "query_string": b"",
                },
            )

        self.assertTrue(resolved_user.is_anonymous)
        validate_token_mock.assert_not_called()


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
)
class JobChatWebSocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.client_user = user_model.objects.create_user(
            username="ws-client",
            email="ws-client@example.com",
            password="testpass123",
            email_verified=True,
        )
        self.organization_owner = user_model.objects.create_user(
            username="ws-owner",
            email="ws-owner@example.com",
            password="testpass123",
            email_verified=True,
        )
        self.outsider = user_model.objects.create_user(
            username="ws-outsider",
            email="ws-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )
        self.organization = Organization.objects.create(
            user=self.organization_owner,
            name="Websocket Org",
            legal_name="Websocket Org SL",
            tax_id="W100",
            billing_email="billing@ws-org.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
        )
        service = Service.objects.create(
            organization=self.organization,
            name="Websocket Plan",
            description="",
        )
        service_price = ServicePrice.objects.create(
            service=service,
            amount="99.99",
            currency="EUR",
            effective_from=date(2026, 1, 1),
        )
        self.job = Job.objects.create(
            user=self.client_user,
            organization=self.organization,
            plan_price=service_price,
            status=Job.Status.PENDING,
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _build_path(self):
        return f"/ws/jobs/{self.job.uuid}/chat/"

    def _build_headers(self, token=None):
        if not token:
            return []
        return [(b"authorization", f"Bearer {token}".encode("utf-8"))]

    def _access_token(self, user):
        return str(RefreshToken.for_user(user).access_token)

    def _ws_application(self):
        return JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))

    async def _close_communicator(self, communicator):
        await communicator.disconnect()
        await communicator.wait()

    def test_rejects_connection_when_token_is_missing(self):
        async def scenario():
            communicator = WebsocketCommunicator(self._ws_application(), self._build_path())
            try:
                return await communicator.connect()
            finally:
                await communicator.wait()

        connected, close_code = async_to_sync(scenario)()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    def test_rejects_connection_when_token_is_only_sent_in_query_string(self):
        async def scenario():
            legacy_token = self._access_token(self.client_user)
            communicator = WebsocketCommunicator(
                self._ws_application(),
                f"{self._build_path()}?token={legacy_token}",
            )
            try:
                return await communicator.connect()
            finally:
                await communicator.wait()

        connected, close_code = async_to_sync(scenario)()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    def test_rejects_connection_when_user_is_not_job_member(self):
        async def scenario():
            outsider_token = self._access_token(self.outsider)
            communicator = WebsocketCommunicator(
                self._ws_application(),
                self._build_path(),
                headers=self._build_headers(outsider_token),
            )
            try:
                return await communicator.connect()
            finally:
                await communicator.wait()

        connected, close_code = async_to_sync(scenario)()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    def test_rejects_connection_when_user_is_not_verified(self):
        unverified_user = get_user_model().objects.create_user(
            username="ws-unverified",
            email="ws-unverified@example.com",
            password="testpass123",
            email_verified=False,
        )

        async def scenario():
            token = self._access_token(unverified_user)
            communicator = WebsocketCommunicator(
                self._ws_application(),
                self._build_path(),
                headers=self._build_headers(token),
            )
            try:
                return await communicator.connect()
            finally:
                await communicator.wait()

        connected, close_code = async_to_sync(scenario)()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    def test_z_member_can_send_and_receive_chat_message(self):
        async def scenario():
            token = self._access_token(self.client_user)
            communicator = WebsocketCommunicator(
                self._ws_application(),
                self._build_path(),
                headers=self._build_headers(token),
            )
            connected, _ = await communicator.connect()
            if not connected:
                return False, None

            try:
                await communicator.send_json_to({"content": "hola websocket"})
                payload = await communicator.receive_json_from()
                return True, payload
            finally:
                await self._close_communicator(communicator)

        connected, payload = async_to_sync(scenario)()
        self.assertTrue(connected)
        self.assertIsNotNone(payload)

        self.assertEqual(payload["content"], "hola websocket")
        self.assertEqual(payload["sender"], self.client_user.id)

    def test_rejects_message_send_when_membership_is_revoked_after_connect(self):
        async def scenario():
            token = self._access_token(self.client_user)
            communicator = WebsocketCommunicator(
                self._ws_application(),
                self._build_path(),
                headers=self._build_headers(token),
            )
            connected, _ = await communicator.connect()
            if not connected:
                return False, None

            try:
                await database_sync_to_async(Job.objects.filter(pk=self.job.pk).update)(user=self.outsider)
                await communicator.send_json_to({"content": "should fail"})
                payload = await communicator.receive_json_from()
                return True, payload
            finally:
                await self._close_communicator(communicator)

        connected, payload = async_to_sync(scenario)()

        self.assertTrue(connected)
        self.assertEqual(payload["detail"], "You do not have access to this job.")
        self.assertFalse(JobChatMessage.objects.filter(content="should fail").exists())

    @override_settings(JOB_CHAT_WS_RATE_LIMIT=1, JOB_CHAT_WS_RATE_WINDOW=60)
    def test_rate_limits_websocket_messages(self):
        async def scenario():
            token = self._access_token(self.client_user)
            communicator = WebsocketCommunicator(
                self._ws_application(),
                self._build_path(),
                headers=self._build_headers(token),
            )
            connected, _ = await communicator.connect()
            if not connected:
                return False, None, None

            try:
                await communicator.send_json_to({"content": "first"})
                first_payload = await communicator.receive_json_from()
                await communicator.send_json_to({"content": "second"})
                second_payload = await communicator.receive_json_from()
                return True, first_payload, second_payload
            finally:
                await self._close_communicator(communicator)

        connected, first_payload, second_payload = async_to_sync(scenario)()

        self.assertTrue(connected)
        self.assertEqual(first_payload["content"], "first")
        self.assertEqual(second_payload["detail"], "Rate limit exceeded.")
        self.assertFalse(JobChatMessage.objects.filter(content="second").exists())
