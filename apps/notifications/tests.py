from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.job_chat.models import JobChat, JobChatMessage
from apps.notifications.models import Notification, NotificationPreference, NotificationRecipient
from apps.notifications.services import emit_job_chat_message_notification, send_email_notification
from apps.organization.models import Announcement, Category, Organization


class NotificationApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="notif-admin",
            email="notif-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.user = user_model.objects.create_user(
            username="notif-user",
            email="notif-user@example.com",
            password="testpass123",
        )
        self.other_user = user_model.objects.create_user(
            username="notif-other",
            email="notif-other@example.com",
            password="testpass123",
        )
        self.notification = Notification.objects.create(
            origin=Notification.Origin.SYSTEM,
            category=Notification.Category.SYSTEM,
            severity=Notification.Severity.MEDIUM,
            target_type=Notification.TargetType.USER,
            target_uuid=self.user.uuid,
            title="Account updated",
            body="Your account status changed.",
            requested_channels=[Notification.Channel.IN_APP],
        )
        self.recipient = NotificationRecipient.objects.create(
            notification=self.notification,
            user=self.user,
            in_app_enabled=True,
        )
        NotificationRecipient.objects.create(
            notification=self.notification,
            user=self.other_user,
            in_app_enabled=True,
        )

    def test_user_list_only_returns_own_recipients(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("notifications-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.recipient.uuid))

    def test_user_can_mark_notification_as_read(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(reverse("notifications-read", kwargs={"uuid": self.recipient.uuid}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.recipient.refresh_from_db()
        self.assertIsNotNone(self.recipient.read_at)

    def test_user_can_mark_all_notifications_as_read(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(reverse("notifications-mark-all-read"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.recipient.refresh_from_db()
        self.assertEqual(response.data["updated_count"], 1)
        self.assertIsNotNone(self.recipient.read_at)

    def test_unread_count_endpoint_returns_pending_count(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("notifications-unread-count"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 1)

    def test_admin_can_send_notification_to_organization(self):
        organization = Organization.objects.create(
            user=self.user,
            name="Provider One",
            legal_name="Provider One LLC",
            tax_id="ES123",
            billing_email="billing@example.com",
            billing_address="Street 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
        )
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-notifications-send"),
            {
                "title": "Provider update",
                "body": "There is an update for your organization.",
                "target_type": "organization",
                "target_uuid": str(organization.uuid),
                "category": "system",
                "severity": "medium",
                "channels": ["in_app", "email"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["target_type"], "organization")
        self.assertEqual(NotificationRecipient.objects.filter(notification__uuid=response.data["uuid"]).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_preferences_can_disable_external_delivery_without_hiding_inbox(self):
        NotificationPreference.objects.create(
            user=self.user,
            in_app_enabled=True,
            email_enabled=False,
            push_enabled=False,
            system_notifications=True,
            chat_notifications=True,
            marketing_notifications=True,
        )
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-notifications-send"),
            {
                "title": "No email",
                "body": "Inbox only",
                "target_type": "user",
                "target_uuid": str(self.user.uuid),
                "category": "system",
                "severity": "low",
                "channels": ["in_app", "email"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        recipient = NotificationRecipient.objects.get(notification__uuid=response.data["uuid"], user=self.user)
        self.assertTrue(recipient.in_app_enabled)
        self.assertFalse(recipient.email_enabled)

    def test_email_failures_are_recorded_and_logged_not_raised(self):
        with (
            patch("apps.notifications.services.send_mail", side_effect=OSError("SMTP unreachable")),
            self.assertLogs("apps.notifications.services", level="ERROR"),
        ):
            send_email_notification(self.recipient)

        self.recipient.refresh_from_db()
        self.assertEqual(self.recipient.email_status, NotificationRecipient.DeliveryStatus.FAILED)
        dispatch = self.recipient.dispatches.get()
        self.assertIn("SMTP unreachable", dispatch.error_message)


class NotificationProducerTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-admin",
            email="management-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.customer = user_model.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="testpass123",
        )
        self.provider_user = user_model.objects.create_user(
            username="provider-user",
            email="provider@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(name="Electricidad", description="Servicios")
        self.organization = Organization.objects.create(
            user=self.provider_user,
            name="Provider Two",
            legal_name="Provider Two LLC",
            tax_id="ES999",
            billing_email="provider-billing@example.com",
            billing_address="Street 2",
            billing_city="Barcelona",
            billing_country="ES",
            billing_postal_code="08001",
        )
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Urgent repair",
            location="Madrid",
            announcement="Need help",
        )

    def test_management_user_deactivate_creates_notification(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(reverse("management-users-deactivate", kwargs={"uuid": self.customer.uuid}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.customer,
                notification__origin=Notification.Origin.MANAGEMENT,
            ).exists()
        )

    def test_job_chat_message_producer_notifies_other_participant(self):
        from apps.jobs.models import Job

        job = Job.objects.create(
            user=self.customer,
            announcement=self.announcement,
        )
        chat = JobChat.objects.create(job=job)
        message = JobChatMessage.objects.create(
            job_chat=chat,
            user=self.customer,
            content="Hola proveedor",
        )

        emit_job_chat_message_notification(message)

        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.provider_user,
                notification__origin=Notification.Origin.JOB_CHAT,
            ).exists()
        )
