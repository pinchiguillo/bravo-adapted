import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assets.models import Asset
from apps.jobs.models import Job
from apps.organization.models import Announcement, Category, Organization

from .models import JobChat, JobChatMessage


class JobChatTestCase(APITestCase):
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
            billing_email="billing@acme.example.com",
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


class JobChatApiTests(JobChatTestCase):
    def test_provider_can_get_job_chat_messages(self):
        self.client.force_authenticate(user=self.provider_user)

        response = self.client.get(reverse("job-chat-messages", kwargs={"job_uuid": self.job.uuid}))

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

        response = self.client.get(reverse("job-chat-messages", kwargs={"job_uuid": self.job.uuid}))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProposalWidgetTests(JobChatTestCase):
    """Price proposals: server-validated content and server-owned status."""

    def _proposal(self, **overrides):
        data = {
            "title": "Deep clean",
            "description": "Full flat",
            "price": 120.5,
            "price_mode": "total",
            "currency": "EUR",
        }
        data.update(overrides)
        return json.dumps({"widget_type": "proposal", "data": data})

    def _send(self, user, content, message_type="widget"):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("job-chat-send", kwargs={"job_uuid": self.job.uuid}),
            {"type": message_type, "content": content},
            format="json",
        )

    def _answer(self, user, message_uuid, answer):
        self.client.force_authenticate(user=user)
        return self.client.patch(
            reverse("update-proposal-status", kwargs={"job_uuid": self.job.uuid, "message_uuid": message_uuid}),
            {"status": answer},
            format="json",
        )

    def test_new_proposal_is_always_pending_and_keeps_price_as_number(self):
        response = self._send(self.provider_user, self._proposal(status="accepted", injected="x"))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        widget = json.loads(response.data["content"])
        self.assertEqual(widget["data"]["status"], "pending")
        self.assertEqual(widget["data"]["price"], 120.5)
        self.assertNotIn("injected", widget["data"])

    def test_invalid_proposals_are_rejected(self):
        cases = {
            "negative price": self._proposal(price=-1),
            "three decimals": self._proposal(price="10.123"),
            "unknown currency": self._proposal(currency="XXX"),
            "missing title": self._proposal(title=""),
            "no data": json.dumps({"widget_type": "proposal"}),
            "unknown widget": json.dumps({"widget_type": "invoice", "data": {}}),
            "not json": "{not json",
            "json array": json.dumps([1, 2]),
        }
        for label, content in cases.items():
            with self.subTest(label):
                self.assertEqual(self._send(self.provider_user, content).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(JobChatMessage.objects.filter(type=JobChatMessage.MessageType.WIDGET).exists())

    def test_unknown_message_type_is_rejected(self):
        response = self._send(self.provider_user, "hello", message_type="system")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_participant_can_accept_a_pending_proposal(self):
        proposal = self._send(self.provider_user, self._proposal()).data

        response = self._answer(self.customer, proposal["uuid"], "accepted")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json.loads(response.data["content"])["data"]["status"], "accepted")

    def test_accepting_a_proposal_starts_a_pending_job(self):
        self.job.status = Job.Status.PENDING
        self.job.save(update_fields=["status"])
        proposal = self._send(self.provider_user, self._proposal()).data

        self._answer(self.customer, proposal["uuid"], "accepted")

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.ACTIVE)

    def test_rejecting_a_proposal_leaves_the_job_pending(self):
        self.job.status = Job.Status.PENDING
        self.job.save(update_fields=["status"])
        proposal = self._send(self.provider_user, self._proposal()).data

        self._answer(self.customer, proposal["uuid"], "rejected")

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.PENDING)

    def test_author_cannot_answer_their_own_proposal(self):
        proposal = self._send(self.provider_user, self._proposal()).data

        response = self._answer(self.provider_user, proposal["uuid"], "accepted")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_answered_proposal_cannot_change(self):
        proposal = self._send(self.provider_user, self._proposal()).data
        self._answer(self.customer, proposal["uuid"], "rejected")

        response = self._answer(self.customer, proposal["uuid"], "accepted")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        message = JobChatMessage.objects.get(uuid=proposal["uuid"])
        self.assertEqual(json.loads(message.content)["data"]["status"], "rejected")

    def test_answering_a_plain_text_message_is_rejected(self):
        response = self._answer(self.provider_user, self.first_message.uuid, "accepted")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_outsider_cannot_answer_a_proposal(self):
        proposal = self._send(self.provider_user, self._proposal()).data

        response = self._answer(self.outsider, proposal["uuid"], "accepted")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_failing_broadcast_does_not_fail_a_stored_message(self):
        with (
            patch("apps.job_chat.services.get_channel_layer", side_effect=RuntimeError("redis down")),
            self.assertLogs("apps.job_chat.services", level="ERROR"),
        ):
            response = self._send(self.provider_user, "stored anyway", message_type="plain_text")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(JobChatMessage.objects.filter(content="stored anyway").exists())

    def test_a_failing_notification_does_not_lose_the_message(self):
        with (
            patch("apps.job_chat.services.emit_job_chat_message_notification", side_effect=RuntimeError("smtp down")),
            self.assertLogs("apps.job_chat.services", level="ERROR"),
        ):
            response = self._send(self.provider_user, "still delivered", message_type="plain_text")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(JobChatMessage.objects.filter(content="still delivered").exists())


class JobChatAttachmentTests(JobChatTestCase):
    def _confirmed_asset(self, owner):
        return Asset.objects.create(
            owner=owner,
            kind=Asset.Kind.JOB_CHAT_ATTACHMENT,
            visibility="protected",
            status=Asset.Status.CONFIRMED,
            key=f"assets/job_chat_attachment/{owner.pk}/{Asset.objects.count()}.pdf",
            original_filename="quote.pdf",
            content_type_client="application/pdf",
            size_client=10,
        )

    def _attach(self, user, message, asset):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("job-chat-attach", kwargs={"job_uuid": self.job.uuid, "message_uuid": message.uuid}),
            {"asset_id": str(asset.id)},
            format="json",
        )

    def _message_from(self, user):
        return JobChatMessage.objects.create(job_chat=self.chat, user=user, content="see attached")

    def test_provider_can_attach_to_their_own_message(self):
        asset = self._confirmed_asset(self.provider_user)

        response = self._attach(self.provider_user, self._message_from(self.provider_user), asset)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.ATTACHED)

    def test_participants_cannot_attach_to_the_other_partys_message(self):
        asset = self._confirmed_asset(self.customer)

        response = self._attach(self.customer, self._message_from(self.provider_user), asset)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsiders_cannot_attach(self):
        asset = self._confirmed_asset(self.outsider)

        response = self._attach(self.outsider, self.first_message, asset)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_an_asset_can_only_be_attached_once(self):
        asset = self._confirmed_asset(self.customer)
        self._attach(self.customer, self.first_message, asset)

        response = self._attach(self.customer, self._message_from(self.customer), asset)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(asset.job_chat_attachments.count(), 1)

    def test_attaching_an_asset_that_was_attached_meanwhile_is_rejected(self):
        from rest_framework.exceptions import ValidationError
        from rest_framework.test import APIRequestFactory

        from .serializers import JobChatAttachmentCreateSerializer

        asset = self._confirmed_asset(self.customer)
        stale_copy = Asset.objects.get(pk=asset.pk)
        Asset.objects.filter(pk=asset.pk).update(status=Asset.Status.ATTACHED)
        request = APIRequestFactory().post("/")
        request.user = self.customer
        serializer = JobChatAttachmentCreateSerializer(
            data={"asset_id": str(asset.id)},
            context={"request": request, "message": self.first_message, "asset": stale_copy},
        )
        serializer._validated_data = {"asset_id": asset.id}
        serializer._errors = {}

        with self.assertRaises(ValidationError):
            serializer.save()
        self.assertEqual(asset.job_chat_attachments.count(), 0)


@override_settings(JOB_CHAT_HISTORY_PAGE_SIZE=2)
class JobChatHistoryPaginationTests(JobChatTestCase):
    def setUp(self):
        super().setUp()
        # first_message plus four more: five in total, oldest first.
        for index in range(4):
            JobChatMessage.objects.create(job_chat=self.chat, user=self.customer, content=f"message {index}")
        self.client.force_authenticate(user=self.customer)

    def _page(self, before=None):
        params = {"before": before} if before else {}
        response = self.client.get(reverse("job-chat-messages", kwargs={"job_uuid": self.job.uuid}), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [message["content"] for message in response.data["messages"]], response.data

    def test_first_page_is_the_newest_messages_oldest_first(self):
        contents, data = self._page()

        self.assertEqual(contents, ["message 2", "message 3"])
        self.assertTrue(data["has_more"])

    def test_pages_walk_back_to_the_start_without_gaps_or_duplicates(self):
        seen = []
        before = None
        while True:
            contents, data = self._page(before)
            seen = contents + seen
            if not data["has_more"]:
                break
            before = data["messages"][0]["uuid"]

        self.assertEqual(seen, [self.first_message.content, "message 0", "message 1", "message 2", "message 3"])

    def test_unknown_cursor_returns_404(self):
        response = self.client.get(
            reverse("job-chat-messages", kwargs={"job_uuid": self.job.uuid}), {"before": "not-a-uuid"}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
