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
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken

from job_chat.models import JobChatAttachment, JobChatMessage
from job_chat.routing import websocket_urlpatterns
from job_chat.views import JobChatViewSet
from job_chat.ws_auth import JWTAuthMiddleware, JWTAuthMiddlewareStack
from organization.models import (
    Announcement,
    Category,
    Organization,
    OrganizationJob,
    Service,
    ServicePrice,
    Subservice,
)

from .models import Job
from .views import JobViewSet, job_search_parameter


class JobAttachmentDownloadUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.chat = object()

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

        request = self.factory.get("/api/jobs/chats/chat/messages/1/attachments/2/download/")
        view = JobChatViewSet()
        view.request = request
        view.get_object = lambda: self.chat

        with patch("job_chat.views.JobChatAttachment.objects.select_related") as select_related_mock:
            queryset = select_related_mock.return_value
            queryset.filter.return_value.first.return_value = attachment
            response = view.download_attachment(request, uuid="chat", message_id="1", attachment_id="2")

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

        request = self.factory.get("/api/jobs/chats/chat/messages/1/attachments/2/download/")
        view = JobChatViewSet()
        view.request = request
        view.get_object = lambda: self.chat

        with patch("job_chat.views.JobChatAttachment.objects.select_related") as select_related_mock:
            queryset = select_related_mock.return_value
            queryset.filter.return_value.first.return_value = attachment
            response = view.download_attachment(request, uuid="chat", message_id="1", attachment_id="2")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["download_url"].startswith("http://testserver/media/"))
        self.assertEqual(response.data["expires_in"], 120)
        self.assertEqual(response.data["filename"], "proof.txt")


class JobMessagesPaginationTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_messages_get_is_paginated(self):
        request = Request(self.factory.get("/api/jobs/chats/chat/messages/", {"page_size": 1}))
        view = JobChatViewSet()
        view.request = request
        view.action = "messages"
        view.get_object = lambda: SimpleNamespace()

        with patch("job_chat.views.JobChatMessage.objects.select_related") as select_related_mock:
            queryset = select_related_mock.return_value
            queryset.prefetch_related.return_value.filter.return_value.order_by.return_value = [
                SimpleNamespace(id=1),
                SimpleNamespace(id=2),
            ]
            with patch("job_chat.views.JobChatMessageSerializer") as serializer_mock:
                serializer_mock.return_value.data = [{"id": 1}]

                response = view.messages(request, uuid="chat")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"], [{"id": 1}])
        self.assertIsNotNone(response.data["next"])


class JobListSearchViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_list_without_filters_returns_queryset(self):
        request = SimpleNamespace(query_params={}, user=SimpleNamespace(is_staff=True))
        view = JobViewSet()
        view.request = request
        view.action = "list"

        class FakeQuerySet:
            def __init__(self):
                self.filter_calls = []

            def filter(self, *args, **kwargs):
                self.filter_calls.append((args, kwargs))
                return self

            def distinct(self):
                return self

        queryset = FakeQuerySet()
        view.queryset = queryset

        result = view.get_queryset()

        self.assertIs(result, queryset)
        self.assertEqual(queryset.filter_calls, [])

    def test_list_contract_keeps_search_optional_in_schema_and_runtime(self):
        request = SimpleNamespace(query_params={}, user=SimpleNamespace(is_staff=True))
        view = JobViewSet()
        view.request = request

        self.assertEqual(view._get_search_query(), "")
        self.assertFalse(job_search_parameter.required)

    def test_list_rejects_short_search_query(self):
        request = SimpleNamespace(query_params={"search": "Ac"}, user=SimpleNamespace(is_staff=True))
        view = JobViewSet()
        view.request = request
        view.action = "list"

        with self.assertRaises(ValidationError) as exc:
            view.get_queryset()

        self.assertEqual(
            exc.exception.detail["search"],
            "Ensure this query parameter has at least 3 characters.",
        )

    def test_list_applies_category_and_search_filters_to_queryset(self):
        class FakeQuerySet:
            def __init__(self):
                self.filter_calls = []

            def filter(self, *args, **kwargs):
                self.filter_calls.append((args, kwargs))
                return self

            def distinct(self):
                return self

        queryset = FakeQuerySet()
        request = SimpleNamespace(
            query_params={"categories": ["cat-uuid"], "search": "Acm"},
            user=SimpleNamespace(is_staff=True),
        )
        view = JobViewSet()
        view.request = request
        view.action = "list"
        view.queryset = queryset

        result = view.get_queryset()

        self.assertIs(result, queryset)
        self.assertEqual(len(queryset.filter_calls), 2)
        self.assertEqual(
            queryset.filter_calls[0][1],
            {"announcement__category__uuid__in": ["cat-uuid"]},
        )
        search_filter = queryset.filter_calls[1][0][0]
        self.assertIn(("announcement__organization__name__icontains", "Acm"), search_filter.children)


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
        self.organization_job = OrganizationJob.objects.create(
            organization=self.organization,
            name="Home Services",
            description="Primary org job",
        )
        self.category, _ = Category.objects.get_or_create(
            name="General",
            defaults={"description": "Categoria general"},
        )
        self.service = Service.objects.create(
            job=self.organization_job,
            category=self.category,
            name="Plan",
            description="",
        )
        self.subservice = Subservice.objects.create(
            service=self.service,
            name="Plan Variant",
            description="",
        )
        self.service_price = ServicePrice.objects.create(
            subservice=self.subservice,
            amount="99.99",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Plan Announcement",
            location="Madrid",
            announcement="Plan disponible",
        )
        self.announcement.services.add(self.service)
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
        self.second_organization_job = OrganizationJob.objects.create(
            organization=self.second_organization,
            name="Client Services",
            description="Secondary org job",
        )
        self.second_service = Service.objects.create(
            job=self.second_organization_job,
            category=self.category,
            name="Second Plan",
            description="",
        )
        self.second_subservice = Subservice.objects.create(
            service=self.second_service,
            name="Second Variant",
            description="",
        )
        self.second_service_price = ServicePrice.objects.create(
            subservice=self.second_subservice,
            amount="49.99",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        self.second_announcement = Announcement.objects.create(
            organization=self.second_organization,
            category=self.category,
            name="Second Announcement",
            location="Valencia",
            announcement="Segundo plan disponible",
        )
        self.second_announcement.services.add(self.second_service)

    def create_job(self, **overrides):
        payload = {
            "user": self.client_user,
            "announcement": self.announcement,
            "plan_price": self.service_price,
            "status": Job.Status.PENDING,
        }
        payload.update(overrides)
        return Job.objects.create(**payload)

    def test_create_job_creates_chat(self):
        self.client.force_authenticate(user=self.client_user)

        response = self.client.post(
            reverse("jobs-list"),
            {
                "announcement": self.announcement.id,
                "plan_price": self.service_price.id,
                "status": Job.Status.PENDING,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        job = Job.objects.get(id=response.data["id"])
        self.assertTrue(hasattr(job, "chat"))
        self.assertIsNotNone(job.chat.uuid)
        self.assertEqual(response.data["chat_uuid"], str(job.chat.uuid))

    def test_job_chat_detail_returns_chat_for_member(self):
        job = self.create_job()

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(reverse("job-chats-detail", kwargs={"uuid": job.chat.uuid}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(job.chat.uuid))
        self.assertEqual(response.data["job"], job.id)

    def test_create_job_rejects_non_pending_status(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("jobs-list"),
            {
                "announcement": self.announcement.id,
                "plan_price": self.service_price.id,
                "status": Job.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_job_member_cannot_change_status_directly(self):
        job = self.create_job()

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

    def test_job_member_cannot_change_announcement_or_plan_price(self):
        job = self.create_job()

        self.client.force_authenticate(user=self.client_user)
        response = self.client.patch(
            reverse("jobs-detail", kwargs={"uuid": job.uuid}),
            {
                "announcement": self.second_announcement.id,
                "plan_price": self.second_service_price.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("announcement", response.data)
        self.assertIn("plan_price", response.data)
        job.refresh_from_db()
        self.assertEqual(job.announcement_id, self.announcement.id)
        self.assertEqual(job.plan_price_id, self.service_price.id)

    def test_job_member_can_rate_completed_job(self):
        job = self.create_job(status=Job.Status.COMPLETED)

        self.client.force_authenticate(user=self.client_user)
        response = self.client.patch(
            reverse("jobs-detail", kwargs={"uuid": job.uuid}),
            {"organization_rating": "4.50"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        job.refresh_from_db()
        self.assertEqual(str(job.organization_rating), "4.50")

    def test_job_member_cannot_rate_non_completed_job(self):
        job = self.create_job()

        self.client.force_authenticate(user=self.client_user)
        response = self.client.patch(
            reverse("jobs-detail", kwargs={"uuid": job.uuid}),
            {"organization_rating": "4.50"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["organization_rating"][0],
            "Organization rating can only be set for completed jobs.",
        )
        job.refresh_from_db()
        self.assertIsNone(job.organization_rating)

    def test_non_member_cannot_partial_update_job(self):
        outsider = get_user_model().objects.create_user(
            username="jobs-update-outsider",
            email="jobs-update-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )
        job = self.create_job()

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
        job = self.create_job()

        self.client.force_authenticate(user=self.client_user)
        response = self.client.delete(reverse("jobs-detail", kwargs={"uuid": job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Job.objects.filter(uuid=job.uuid).exists())

    def test_admin_can_delete_job(self):
        job = self.create_job()

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
        job = self.create_job()

        self.client.force_authenticate(user=outsider)
        response = self.client.get(reverse("job-chats-messages", kwargs={"uuid": job.chat.uuid}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_job_list_is_scoped_to_member_jobs(self):
        owner_job = self.create_job()
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
        outsider_org_job = OrganizationJob.objects.create(
            organization=outsider_org,
            name="Outsider Services",
            description="Outsider org job",
        )
        outsider_service = Service.objects.create(
            job=outsider_org_job,
            category=self.category,
            name="Out Plan",
            description="",
        )
        outsider_subservice = Subservice.objects.create(
            service=outsider_service,
            name="Out Variant",
            description="",
        )
        outsider_price = ServicePrice.objects.create(
            subservice=outsider_subservice,
            amount="10.00",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        outsider_announcement = Announcement.objects.create(
            organization=outsider_org,
            category=self.category,
            name="Out Announcement",
            location="Sevilla",
            announcement="Out plan disponible",
        )
        outsider_announcement.services.add(outsider_service)
        outsider_job = Job.objects.create(
            user=outsider,
            announcement=outsider_announcement,
            plan_price=outsider_price,
            status=Job.Status.PENDING,
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(reverse("jobs-list"), {"search": "Acm"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_job_ids = {item["id"] for item in response.data["results"]}
        self.assertIn(owner_job.id, returned_job_ids)
        self.assertNotIn(outsider_job.id, returned_job_ids)

    def test_job_list_without_filters_returns_member_jobs(self):
        self.client.force_authenticate(user=self.client_user)
        first_job = self.create_job()
        second_job = self.create_job(
            announcement=self.second_announcement,
            plan_price=self.second_service_price,
        )

        response = self.client.get(reverse("jobs-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_job_ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(returned_job_ids, {first_job.id, second_job.id})
        returned_chat_uuids = {item["chat_uuid"] for item in response.data["results"]}
        self.assertEqual(
            returned_chat_uuids,
            {str(first_job.chat.uuid), str(second_job.chat.uuid)},
        )

    def test_job_list_rejects_short_search_query(self):
        self.client.force_authenticate(user=self.client_user)

        response = self.client.get(reverse("jobs-list"), {"search": "Ac"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["search"], "Ensure this query parameter has at least 3 characters.")

    def test_job_list_filters_results_by_search_query(self):
        matching_job = self.create_job()
        other_job = self.create_job(
            announcement=self.second_announcement,
            plan_price=self.second_service_price,
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(reverse("jobs-list"), {"search": "Acm"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        returned_job_ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(returned_job_ids, {matching_job.id})
        self.assertNotIn(other_job.id, returned_job_ids)

    def test_job_list_filters_results_by_categories(self):
        garden_category = Category.objects.create(name="Garden", description="Jardineria")
        garden_service = Service.objects.create(
            job=self.second_organization_job,
            category=garden_category,
            name="Garden Plan",
            description="",
        )
        garden_subservice = Subservice.objects.create(
            service=garden_service,
            name="Garden Variant",
            description="",
        )
        garden_price = ServicePrice.objects.create(
            subservice=garden_subservice,
            amount="59.99",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        garden_announcement = Announcement.objects.create(
            organization=self.second_organization,
            category=garden_category,
            name="Garden Announcement",
            location="Valencia",
            announcement="Servicio de jardineria",
        )
        garden_announcement.services.add(garden_service)
        matching_job = self.create_job(
            announcement=garden_announcement,
            plan_price=garden_price,
        )
        other_job = self.create_job()

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(
            reverse("jobs-list"),
            {"categories": [str(garden_category.uuid)]},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        returned_job_ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(returned_job_ids, {matching_job.id})
        self.assertNotIn(other_job.id, returned_job_ids)

    def test_job_list_filters_results_by_legacy_category_param(self):
        matching_job = self.create_job()
        other_job = self.create_job(
            announcement=self.second_announcement,
            plan_price=self.second_service_price,
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(
            reverse("jobs-list"),
            {"category": str(self.category.uuid)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_job_ids = {item["id"] for item in response.data["results"]}
        self.assertIn(matching_job.id, returned_job_ids)
        self.assertIn(other_job.id, returned_job_ids)

    def test_job_list_combines_categories_and_search_filters(self):
        garden_category = Category.objects.create(name="Garden Plus", description="Exterior")
        garden_service = Service.objects.create(
            job=self.second_organization_job,
            category=garden_category,
            name="Garden Plan",
            description="",
        )
        garden_subservice = Subservice.objects.create(
            service=garden_service,
            name="Garden Variant",
            description="",
        )
        garden_price = ServicePrice.objects.create(
            subservice=garden_subservice,
            amount="69.99",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        matching_announcement = Announcement.objects.create(
            organization=self.second_organization,
            category=garden_category,
            name="Garden Saturdays",
            location="Valencia",
            announcement="Disponible fines de semana",
        )
        matching_announcement.services.add(garden_service)
        non_matching_text_announcement = Announcement.objects.create(
            organization=self.second_organization,
            category=garden_category,
            name="Garden Weekdays",
            location="Valencia",
            announcement="Disponible entre semana",
        )
        non_matching_text_announcement.services.add(garden_service)

        matching_job = self.create_job(
            announcement=matching_announcement,
            plan_price=garden_price,
        )
        non_matching_text_job = self.create_job(
            announcement=non_matching_text_announcement,
            plan_price=garden_price,
        )
        non_matching_category_job = self.create_job()

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(
            reverse("jobs-list"),
            {
                "categories": [str(garden_category.uuid)],
                "search": "Saturdays",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        returned_job_ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(returned_job_ids, {matching_job.id})
        self.assertNotIn(non_matching_text_job.id, returned_job_ids)
        self.assertNotIn(non_matching_category_job.id, returned_job_ids)

    def test_create_job_rejects_plan_price_from_another_announcement(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("jobs-list"),
            {
                "announcement": self.announcement.id,
                "plan_price": self.second_service_price.id,
                "status": Job.Status.PENDING,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_price", response.data)

    def test_create_job_message_rejects_blank_content(self):
        job = self.create_job()
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("job-chats-messages", kwargs={"uuid": job.chat.uuid}),
            {"content": "   "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content", response.data)

    def test_upload_attachment_requires_job_membership(self):
        job = self.create_job()
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        outsider = get_user_model().objects.create_user(
            username="attachment-outsider",
            email="attachment-outsider@example.com",
            password="testpass123",
            email_verified=True,
        )

        self.client.force_authenticate(user=outsider)
        response = self.client.post(
            reverse("job-chats-attachments", kwargs={"uuid": job.chat.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(JobChatAttachment.objects.count(), 0)

    def test_upload_attachment_returns_404_when_message_not_found(self):
        job = self.create_job()
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("job-chats-attachments", kwargs={"uuid": job.chat.uuid, "message_id": 999999}),
            {"file": SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_attachment_succeeds_for_job_member(self):
        job = self.create_job()
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse("job-chats-attachments", kwargs={"uuid": job.chat.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(JobChatAttachment.objects.count(), 1)
        self.assertIn("download_url", response.data)
        self.assertIn("filename", response.data)
        self.assertNotIn("file", response.data)

    def test_upload_attachment_requires_message_sender(self):
        job = self.create_job()
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")

        self.client.force_authenticate(user=self.organization_owner)
        response = self.client.post(
            reverse("job-chats-attachments", kwargs={"uuid": job.chat.uuid, "message_id": message.id}),
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
        job = self.create_job()
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        self.client.force_authenticate(user=self.client_user)

        invalid_type_response = self.client.post(
            reverse("job-chats-attachments", kwargs={"uuid": job.chat.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.pdf", b"abcd", content_type="application/pdf")},
            format="multipart",
        )
        oversize_response = self.client.post(
            reverse("job-chats-attachments", kwargs={"uuid": job.chat.uuid, "message_id": message.id}),
            {"file": SimpleUploadedFile("proof.txt", b"abcde", content_type="text/plain")},
            format="multipart",
        )

        self.assertEqual(invalid_type_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", invalid_type_response.data)
        self.assertEqual(oversize_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", oversize_response.data)
        self.assertEqual(JobChatAttachment.objects.count(), 0)

    def test_upload_attachment_rejects_mismatched_file_signature(self):
        job = self.create_job()
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        self.client.force_authenticate(user=self.client_user)

        response = self.client.post(
            reverse("job-chats-attachments", kwargs={"uuid": job.chat.uuid, "message_id": message.id}),
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
        job = self.create_job()

        self.client.force_authenticate(user=outsider)
        response = self.client.get(reverse("jobs-detail", kwargs={"uuid": job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_job_detail_exposes_chat_uuid_for_member(self):
        job = self.create_job()

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(reverse("jobs-detail", kwargs={"uuid": job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["chat_uuid"], str(job.chat.uuid))

    def test_unverified_user_cannot_access_jobs_api(self):
        unverified_user = get_user_model().objects.create_user(
            username="jobs-unverified",
            email="jobs-unverified@example.com",
            password="testpass123",
            email_verified=False,
        )

        self.client.force_authenticate(user=unverified_user)
        response = self.client.get(reverse("jobs-list"), {"search": "Acm"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Email is not verified.")

    @override_settings(AUTH_BYPASS_EMAIL_VERIFICATION=True)
    def test_unverified_user_can_access_jobs_api_when_bypass_enabled(self):
        unverified_user = get_user_model().objects.create_user(
            username="jobs-unverified-bypass",
            email="jobs-unverified-bypass@example.com",
            password="testpass123",
            email_verified=False,
        )

        self.client.force_authenticate(user=unverified_user)
        response = self.client.get(reverse("jobs-list"), {"search": "Acm"})

        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_download_attachment_requires_job_access(self):
        job = self.create_job()
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
                "job-chats-download-attachment",
                kwargs={"uuid": job.chat.uuid, "message_id": message.id, "attachment_id": attachment.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_attachment_returns_file_for_job_member(self):
        job = self.create_job()
        message = JobChatMessage.objects.create(chat=job.chat, sender=self.client_user, content="hello")
        attachment = JobChatAttachment.objects.create(
            message=message,
            uploaded_by=self.client_user,
            file=SimpleUploadedFile("proof.txt", b"payload", content_type="text/plain"),
        )

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(
            reverse(
                "job-chats-download-attachment",
                kwargs={"uuid": job.chat.uuid, "message_id": message.id, "attachment_id": attachment.id},
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
        job = self.create_job()
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
                    "job-chats-download-attachment",
                    kwargs={"uuid": job.chat.uuid, "message_id": message.id, "attachment_id": attachment.id},
                )
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["download_url"], "https://files.example.com/presigned")
        self.assertEqual(response.data["expires_in"], 123)
        url_mock.assert_called_once_with(attachment.file.name, expire=123)

    @override_settings(JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS=123)
    def test_download_attachment_falls_back_when_storage_has_no_expire_kwarg(self):
        job = self.create_job()
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
                    "job-chats-download-attachment",
                    kwargs={"uuid": job.chat.uuid, "message_id": message.id, "attachment_id": attachment.id},
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
            first_response = self.client.get(reverse("jobs-list"), {"search": "Acm"})
            second_response = self.client.get(reverse("jobs-list"), {"search": "Acm"})

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_create_job_is_throttled(self):
        cache.clear()
        self.client.force_authenticate(user=self.client_user)
        payload = {
            "announcement": self.announcement.id,
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
        job = self.create_job()
        self.client.force_authenticate(user=self.client_user)

        class JobsMessagesTestThrottle(SimpleRateThrottle):
            scope = "jobs_messages_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        with patch.object(JobChatViewSet, "throttle_classes", [JobsMessagesTestThrottle]):
            first_response = self.client.post(
                reverse("job-chats-messages", kwargs={"uuid": job.chat.uuid}),
                {"content": "first"},
                format="json",
            )
            second_response = self.client.post(
                reverse("job-chats-messages", kwargs={"uuid": job.chat.uuid}),
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
                    "path": "/ws/chats/",
                    "headers": [(b"authorization", b"Bearer valid-token")],
                    "query_string": b"",
                },
            )

        self.assertEqual(resolved_user, user)

    def test_assigns_anonymous_and_logs_when_token_is_invalid(self):
        middleware = JWTAuthMiddleware(app=None)

        with (
            patch.object(middleware.jwt_auth, "get_validated_token", side_effect=InvalidToken("bad token")),
            patch("job_chat.ws_auth.logger.warning") as warning_mock,
        ):
            resolved_user = self._run_middleware(
                middleware,
                {
                    "type": "websocket",
                    "path": "/ws/chats/",
                    "headers": [(b"authorization", b"Bearer secret-token")],
                    "query_string": b"",
                },
            )

        self.assertTrue(resolved_user.is_anonymous)

        warning_mock.assert_called_once()
        warning_extra = warning_mock.call_args.kwargs.get("extra", {})
        self.assertEqual(warning_mock.call_args.args[0], "ws_jwt_auth_failed")
        self.assertEqual(warning_extra.get("reason"), "InvalidToken")
        self.assertEqual(warning_extra.get("path"), "/ws/chats/")
        self.assertEqual(warning_extra.get("token_source"), "authorization_header")
        self.assertNotIn("secret-token", str(warning_mock.call_args))

    def test_assigns_anonymous_when_token_is_missing(self):
        middleware = JWTAuthMiddleware(app=None)
        resolved_user = self._run_middleware(
            middleware,
            {"type": "websocket", "path": "/ws/chats/", "headers": [], "query_string": b""},
        )

        self.assertTrue(resolved_user.is_anonymous)

    def test_ignores_query_string_token_when_authorization_header_is_missing(self):
        middleware = JWTAuthMiddleware(app=None)
        with patch.object(middleware.jwt_auth, "get_validated_token") as validate_token_mock:
            resolved_user = self._run_middleware(
                middleware,
                {
                    "type": "websocket",
                    "path": "/ws/chats/",
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
                    "path": "/ws/chats/",
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
        organization_job = OrganizationJob.objects.create(
            organization=self.organization,
            name="Websocket Services",
            description="Websocket org job",
        )
        service = Service.objects.create(
            job=organization_job,
            category=self.category,
            name="Websocket Plan",
            description="",
        )
        subservice = Subservice.objects.create(
            service=service,
            name="Websocket Variant",
            description="",
        )
        service_price = ServicePrice.objects.create(
            subservice=subservice,
            amount="99.99",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Websocket Announcement",
            location="Madrid",
            announcement="Websocket plan disponible",
        )
        announcement.services.add(service)
        self.job = Job.objects.create(
            user=self.client_user,
            announcement=announcement,
            plan_price=service_price,
            status=Job.Status.PENDING,
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _build_path(self):
        return f"/ws/chats/{self.job.chat.uuid}/"

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
        self.assertEqual(payload["detail"], "You do not have access to this chat.")
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
