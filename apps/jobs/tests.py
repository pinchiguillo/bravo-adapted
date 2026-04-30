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
        self.category = Category.objects.create(
            name="Home Services",
            description="Servicios para el hogar",
        )
        self.organization = Organization.objects.create(
            user=self.other_user,
            name="Acme",
            legal_name="Acme SL",
            tax_id="A123",
            billing_email="billing@acme.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
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

    def test_job_list_requires_authentication(self):
        response = self.client.get(reverse("job-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
