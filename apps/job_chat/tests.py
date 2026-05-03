from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.jobs.models import Job
from apps.organization.models import Announcement, Category, Organization

from .models import JobChat, JobChatMessage


class JobChatApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.customer = user_model.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="testpass123",
        )
        self.provider_user = user_model.objects.create_user(
            username="provider-owner",
            email="provider@example.com",
            password="testpass123",
        )
        self.outsider = user_model.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        self.category = Category.objects.create(
            name="Home Services",
            description="Servicios para el hogar",
        )
        self.organization = Organization.objects.create(
            user=self.provider_user,
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
        self.job = Job.objects.create(
            user=self.customer,
            announcement=self.announcement,
            status=Job.Status.ACTIVE,
        )
        self.chat = JobChat.objects.create(job=self.job)
        self.first_message = JobChatMessage.objects.create(
            job_chat=self.chat,
            user=self.customer,
            type=JobChatMessage.MessageType.PLAIN_TEXT,
            content="Hola, sigo interesado en el servicio.",
        )

    def test_provider_can_get_job_chat_messages(self):
        self.client.force_authenticate(user=self.provider_user)

        response = self.client.get(
            reverse("job-chat-messages", kwargs={"job_uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.chat.uuid))
        self.assertEqual(len(response.data["messages"]), 1)
        self.assertEqual(response.data["messages"][0]["uuid"], str(self.first_message.uuid))

    def test_provider_can_send_job_chat_message(self):
        self.client.force_authenticate(user=self.provider_user)

        response = self.client.post(
            reverse("job-chat-send", kwargs={"job_uuid": self.job.uuid}),
            {"content": "Perfecto, te paso propuesta hoy."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["content"], "Perfecto, te paso propuesta hoy.")
        self.assertEqual(response.data["user_id"], self.provider_user.id)
        self.assertTrue(
            JobChatMessage.objects.filter(
                job_chat=self.chat,
                user=self.provider_user,
                content="Perfecto, te paso propuesta hoy.",
            ).exists()
        )

    def test_outsider_cannot_get_job_chat_messages(self):
        self.client.force_authenticate(user=self.outsider)

        response = self.client.get(
            reverse("job-chat-messages", kwargs={"job_uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
