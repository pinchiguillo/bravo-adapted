import uuid

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMultiAlternatives
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from common.client_ip import get_client_ip
from common.email_backends import SesEmailBackend
from common.exception_handler import exception_handler
from common.exceptions import ConflictError, DomainError, NotFoundError


class S3StorageTests(TestCase):
    """Runs against the moto S3 mock started in conftest.py."""

    def test_avatar_upload_is_persisted_in_s3(self):
        user = get_user_model().objects.create_user(
            username=f"user_{uuid.uuid4().hex[:8]}",
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            password="test-pass-123",
        )
        user.avatar = SimpleUploadedFile(
            "avatar.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )
        user.save()

        self.assertTrue(user.avatar.name.startswith("avatars/"))
        self.assertTrue(user.avatar.storage.exists(user.avatar.name))
        s3 = boto3.client("s3", region_name=settings.AWS_DEFAULT_REGION)
        objects = s3.list_objects_v2(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Prefix=user.avatar.name)
        self.assertEqual(objects["KeyCount"], 1)


class SesEmailBackendTests(TestCase):
    """Runs against the moto SES mock; DEFAULT_FROM_EMAIL is a verified identity there."""

    def setUp(self):
        self.ses = boto3.client("ses", region_name=settings.AWS_DEFAULT_REGION)

    def _sent_count(self):
        return int(self.ses.get_send_quota()["SentLast24Hours"])

    def _message(self, **kwargs):
        defaults = {
            "subject": "SES test",
            "body": "plain body",
            "from_email": settings.DEFAULT_FROM_EMAIL,
            "to": ["receiver@example.com"],
        }
        return EmailMultiAlternatives(**{**defaults, **kwargs})

    def test_sends_plain_and_html_message(self):
        before = self._sent_count()
        message = self._message(reply_to=["support@example.com"])
        message.attach_alternative("<p>html body</p>", "text/html")

        sent = SesEmailBackend().send_messages([message])

        self.assertEqual(sent, 1)
        self.assertEqual(self._sent_count(), before + 1)

    def test_skips_messages_without_recipients(self):
        self.assertEqual(SesEmailBackend().send_messages([self._message(to=[])]), 0)
        self.assertEqual(SesEmailBackend().send_messages([]), 0)

    def test_unverified_sender_raises_unless_fail_silently(self):
        message = self._message(from_email="unverified@example.com")

        with self.assertRaises(ClientError):
            SesEmailBackend().send_messages([message])
        self.assertEqual(SesEmailBackend(fail_silently=True).send_messages([message]), 0)


@override_settings(TRUSTED_PROXY_IPS=["10.0.0.0/8"])
class ClientIpTests(SimpleTestCase):
    def _ip(self, remote_addr, forwarded_for=None):
        extra = {"REMOTE_ADDR": remote_addr}
        if forwarded_for is not None:
            extra["HTTP_X_FORWARDED_FOR"] = forwarded_for
        return get_client_ip(RequestFactory().get("/", **extra))

    def test_forwarded_for_is_ignored_when_the_peer_is_not_a_trusted_proxy(self):
        self.assertEqual(self._ip("203.0.113.5", "198.51.100.1"), "203.0.113.5")

    def test_client_is_the_address_the_trusted_proxy_saw(self):
        self.assertEqual(self._ip("10.0.0.2", "203.0.113.9"), "203.0.113.9")

    def test_spoofed_left_most_entries_are_ignored(self):
        self.assertEqual(self._ip("10.0.0.2", "1.2.3.4, 203.0.113.9"), "203.0.113.9")

    def test_chained_trusted_proxies_are_skipped(self):
        self.assertEqual(self._ip("10.0.0.2", "1.2.3.4, 203.0.113.9, 10.1.1.1"), "203.0.113.9")

    def test_malformed_hop_falls_back_to_the_peer(self):
        self.assertEqual(self._ip("10.0.0.2", "203.0.113.9, not-an-ip"), "10.0.0.2")

    def test_missing_remote_addr_returns_none(self):
        self.assertIsNone(self._ip(""))


class DomainExceptionHandlerTests(SimpleTestCase):
    def test_domain_errors_map_to_their_status_and_code(self):
        cases = ((DomainError("bad"), 400), (NotFoundError("gone"), 404), (ConflictError("taken"), 409))
        for error, expected_status in cases:
            with self.subTest(type(error).__name__):
                response = exception_handler(error, {})

                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.data, {"detail": error.message, "code": error.code})

    def test_field_errors_keep_the_validation_error_shape(self):
        response = exception_handler(DomainError("Not a PNG.", field="file"), {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"file": "Not a PNG."})

    def test_other_exceptions_are_left_to_drf(self):
        self.assertIsNone(exception_handler(ValueError("boom"), {}))
