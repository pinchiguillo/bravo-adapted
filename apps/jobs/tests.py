from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.job_chat.models import JobChat, JobChatMessage
from apps.organization.models import (
    Announcement,
    Category,
    Organization,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)

from .models import Job


class JobApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="job-owner",
            email="job-owner@example.com",
            password="testpass123",
            first_name="Ana",
            last_name="Lopez",
        )
        self.other_user = user_model.objects.create_user(
            username="other-job-owner",
            email="other-job-owner@example.com",
            password="testpass123",
        )
        self.third_user = user_model.objects.create_user(
            username="third-job-owner",
            email="third-job-owner@example.com",
            password="testpass123",
        )
        self.fourth_user = user_model.objects.create_user(
            username="fourth-job-owner",
            email="fourth-job-owner@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(
            name="Home Services",
            description="Servicios para el hogar",
        )
        self.organization = Organization.objects.create(
            user=self.other_user,
            name="Acme",
            legal_name="Acme SL",
            tax_id="A123",
            billing_email="billing@acme.example.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            is_approved=True,
        )
        self.other_organization = Organization.objects.create(
            user=self.third_user,
            name="Other Provider",
            legal_name="Other Provider SL",
            tax_id="B123",
            billing_email="billing@other-provider.example.com",
            billing_address="Second 2",
            billing_city="Barcelona",
            billing_country="ES",
            billing_postal_code="08001",
            is_approved=True,
        )
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Weekend Cleaning",
            location="Madrid",
            announcement="Promo de limpieza",
            status=Announcement.Status.ACTIVE,
            description="Servicio de limpieza a domicilio",
            free_text="Disponible sabados",
        )
        self.other_announcement = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Office Cleaning",
            location="Barcelona",
            announcement="Limpieza de oficina",
            status=Announcement.Status.ACTIVE,
            description="Servicio de limpieza de oficina",
            free_text="Disponible entre semana",
        )
        self.service_catalog = ServiceCatalog.objects.create(
            category=self.category,
            name="Cleaning",
            description="Servicios de limpieza",
        )
        self.subservice = Subservice.objects.create(
            announcement=self.announcement,
            service_catalog=self.service_catalog,
            name="Full cleaning",
            description="Limpieza completa",
        )
        self.price = ServicePrice.objects.create(
            subservice=self.subservice,
            amount="120.00",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
        )
        self.user_job = Job.objects.create(
            user=self.user,
            announcement=self.announcement,
            status=Job.Status.ACTIVE,
            plan_price=self.price,
        )
        self.other_job = Job.objects.create(
            user=self.other_user,
            announcement=self.announcement,
            status=Job.Status.PENDING,
        )
        self.provider_visible_job = Job.objects.create(
            user=self.third_user,
            announcement=self.announcement,
            status=Job.Status.PENDING,
        )
        self.unrelated_provider_job = Job.objects.create(
            user=self.fourth_user,
            announcement=self.other_announcement,
            status=Job.Status.ACTIVE,
        )

        self.user_chat = JobChat.objects.create(job=self.user_job)
        JobChatMessage.objects.create(
            job_chat=self.user_chat,
            user=self.user,
            type=JobChatMessage.MessageType.PLAIN_TEXT,
            content="Hola, necesito presupuesto para el servicio completo.",
        )

    def test_job_list_returns_only_authenticated_users_jobs(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("job-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["uuid"], str(self.user_job.uuid))
        self.assertEqual(response.data[0]["status"], Job.Status.ACTIVE)
        self.assertEqual(response.data[0]["announcement"], str(self.announcement.uuid))
        self.assertEqual(response.data[0]["organization_name"], self.organization.name)
        self.assertEqual(response.data[0]["announcement_name"], self.announcement.name)
        self.assertEqual(response.data[0]["announcement_category"], self.category.name)
        self.assertEqual(
            response.data[0]["user"],
            {
                "uuid": str(self.user.uuid),
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
            },
        )
        self.assertEqual(
            response.data[0]["provider"],
            {
                "uuid": str(self.organization.uuid),
                "name": self.organization.name,
            },
        )
        self.assertEqual(
            response.data[0]["price"],
            {
                "uuid": str(self.price.uuid),
                "amount": "120.00",
                "currency": "EUR",
                "charging_type": ServicePrice.ChargingType.PER_PROJECT,
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
            },
        )
        self.assertEqual(
            response.data[0]["last_message_preview"],
            "Hola, necesito presupuesto para el servicio completo.",
        )
        self.assertEqual(response.data[0]["unread_count"], 0)

    def test_job_list_me_alias_returns_same_payload(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("job-list-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["uuid"], str(self.user_job.uuid))

    def test_job_list_role_provider_returns_jobs_for_owned_announcements(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(reverse("job-list"), {"role": "provider"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["uuid"] for item in response.data},
            {str(self.user_job.uuid), str(self.other_job.uuid), str(self.provider_visible_job.uuid)},
        )
        self.assertEqual(
            {item["provider"]["uuid"] for item in response.data},
            {str(self.organization.uuid)},
        )

    def test_job_list_role_provider_ignores_unrelated_provider_jobs(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(reverse("job-list"), {"role": "provider"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(str(self.unrelated_provider_job.uuid), {item["uuid"] for item in response.data})

    def test_job_list_role_provider_requires_owned_organization(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("job-list"), {"role": "provider"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_job_detail_allows_provider_participant(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(reverse("job-detail", kwargs={"uuid": self.user_job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.user_job.uuid))
        self.assertEqual(response.data["announcement_details"]["uuid"], str(self.announcement.uuid))

    def test_job_list_requires_authentication(self):
        response = self.client.get(reverse("job-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- writes -------------------------------------------------------------

    def _create(self, user, announcement, payload=None):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("announcement-job-create", kwargs={"announcement_uuid": announcement.uuid}),
            payload or {},
            format="json",
        )

    def _patch(self, user, job, payload):
        self.client.force_authenticate(user=user)
        return self.client.patch(reverse("job-detail", kwargs={"uuid": job.uuid}), payload, format="json")

    def test_new_jobs_start_pending_whatever_the_client_sends(self):
        response = self._create(
            self.fourth_user,
            self.announcement,
            {"status": "completed", "organization_rating": "5.00", "plan_price": self.price.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        job = Job.objects.get(uuid=response.data["uuid"])
        self.assertEqual(job.status, Job.Status.PENDING)
        self.assertIsNone(job.organization_rating)
        self.assertEqual(job.plan_price, self.price)

    def test_price_from_another_announcement_is_rejected(self):
        response = self._create(self.fourth_user, self.other_announcement, {"plan_price": self.price.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_price", response.data)

    def test_jobs_cannot_be_opened_on_inactive_announcements(self):
        self.announcement.status = Announcement.Status.SUSPENDED
        self.announcement.save(update_fields=["status"])

        response = self._create(self.fourth_user, self.announcement)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_providers_cannot_request_their_own_announcement(self):
        response = self._create(self.other_user, self.announcement)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requester_cannot_activate_their_own_job(self):
        response = self._patch(self.other_user, self.other_job, {"status": "active"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.other_job.refresh_from_db()
        self.assertEqual(self.other_job.status, Job.Status.PENDING)

    def test_requester_can_complete_and_rate_an_active_job(self):
        response = self._patch(self.user, self.user_job, {"status": "completed", "organization_rating": "4.50"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_job.refresh_from_db()
        self.assertEqual(self.user_job.status, Job.Status.COMPLETED)
        self.assertEqual(str(self.user_job.organization_rating), "4.50")

    def test_ratings_must_be_between_1_and_5_and_only_for_completed_jobs(self):
        not_completed = self._patch(self.user, self.user_job, {"organization_rating": "4.00"})
        out_of_range = self._patch(self.user, self.user_job, {"status": "completed", "organization_rating": "6.00"})

        self.assertEqual(not_completed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(out_of_range.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plan_price_cannot_be_swapped_after_creation(self):
        other_price = ServicePrice.objects.create(
            subservice=self.subservice,
            amount="1.00",
            currency="USD",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )

        self._patch(self.user, self.user_job, {"plan_price": other_price.pk})

        self.user_job.refresh_from_db()
        self.assertEqual(self.user_job.plan_price, self.price)

    def test_active_jobs_cannot_be_deleted_by_the_requester(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(reverse("job-detail", kwargs={"uuid": self.user_job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Job.objects.filter(pk=self.user_job.pk).exists())

    def test_database_rejects_out_of_range_ratings(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Job.objects.filter(pk=self.user_job.pk).update(organization_rating="9.00")

    def test_job_list_query_count_does_not_grow_with_the_number_of_jobs(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_authenticate(user=self.user)

        def list_queries():
            with CaptureQueriesContext(connection) as captured:
                response = self.client.get(reverse("job-list"))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return len(captured), len(response.data)

        baseline_queries, baseline_jobs = list_queries()
        for index in range(3):
            job = Job.objects.create(user=self.user, announcement=self.other_announcement, status=Job.Status.ACTIVE)
            chat = JobChat.objects.create(job=job)
            JobChatMessage.objects.create(job_chat=chat, user=self.user, content=f"message {index}")
        queries, jobs = list_queries()

        self.assertEqual(jobs, baseline_jobs + 3)
        self.assertEqual(queries, baseline_queries)

    def test_job_list_shows_the_latest_message_preview(self):
        JobChatMessage.objects.create(job_chat=self.user_chat, user=self.other_user, content="latest message")
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("job-list"))

        job = next(item for item in response.data if item["uuid"] == str(self.user_job.uuid))
        self.assertEqual(job["last_message_preview"], "latest message")
        self.assertIsNotNone(job["last_message_time"])
