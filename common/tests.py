import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMultiAlternatives, get_connection
from django.test import TestCase


class AwsLocalstackIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s3_enabled = bool(getattr(settings, "USE_S3_STORAGE", False))
        cls.ses_enabled = bool(getattr(settings, "USE_SES_EMAIL", False))
        cls.bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
        cls.sender = getattr(settings, "DEFAULT_FROM_EMAIL", "")

    def setUp(self):
        self.s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_DEFAULT_REGION,
            endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )
        self.ses_client = boto3.client(
            "ses",
            region_name=settings.AWS_DEFAULT_REGION,
            endpoint_url=getattr(settings, "AWS_SES_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )

    def _skip_if_localstack_unavailable(self, callback):
        try:
            callback()
        except (BotoCoreError, ClientError, EndpointConnectionError):
            self.skipTest("Localstack is not reachable from the current test environment.")

    def test_avatar_upload_is_persisted_in_s3(self):
        if not self.s3_enabled:
            self.skipTest("S3 storage is disabled for this environment.")

        self._skip_if_localstack_unavailable(lambda: self.s3_client.list_buckets())
        buckets = self.s3_client.list_buckets().get("Buckets", [])
        if not any(bucket.get("Name") == self.bucket_name for bucket in buckets):
            self.skipTest("Configured S3 bucket is not available in Localstack.")

        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=f"user_{uuid.uuid4().hex[:8]}",
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            password="test-pass-123",
        )
        avatar = SimpleUploadedFile(
            "avatar.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )
        user.avatar = avatar
        user.save()

        self.assertTrue(user.avatar.name.startswith("avatars/"))
        self.assertTrue(user.avatar.storage.exists(user.avatar.name))

        objects = self.s3_client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=user.avatar.name,
        )
        self.assertGreaterEqual(objects.get("KeyCount", 0), 1)

    def test_ses_email_backend_sends_message(self):
        if not self.ses_enabled:
            self.skipTest("SES email backend is disabled for this environment.")

        try:
            identities = self.ses_client.list_identities(IdentityType="EmailAddress")
        except (BotoCoreError, ClientError, EndpointConnectionError):
            self.skipTest("Localstack is not reachable from the current test environment.")
        if self.sender not in identities.get("Identities", []):
            self.skipTest("Configured SES sender is not available in Localstack.")

        email = EmailMultiAlternatives(
            subject="SES Integration Test",
            body="plain body",
            from_email=self.sender,
            to=["receiver@example.com"],
        )
        email.attach_alternative("<p>html body</p>", "text/html")

        sent_count = get_connection().send_messages([email])
        self.assertEqual(sent_count, 1)
