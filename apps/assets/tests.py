import io

import boto3
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Asset


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


class AssetUploadTests(APITestCase):
    """Presigned S3 upload pipeline, against the moto S3 mock from conftest.py."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="uploader", email="uploader@example.com", password="ChangeMe123!", email_verified=True
        )
        self.other_user = user_model.objects.create_user(
            username="other", email="other@example.com", password="ChangeMe123!", email_verified=True
        )
        self.staff = user_model.objects.create_user(
            username="staff", email="staff@example.com", password="ChangeMe123!", email_verified=True, is_staff=True
        )
        self.s3 = boto3.client("s3", region_name=settings.AWS_DEFAULT_REGION)
        self.bucket = settings.AWS_STORAGE_BUCKET_NAME

    def _initiate(self, user=None, **overrides):
        payload = {
            "kind": "job_chat_attachment",
            "filename": "photo.png",
            "content_type": "image/png",
            "size_bytes": len(png_bytes()),
        }
        payload.update(overrides)
        self.client.force_authenticate(user=user or self.user)
        return self.client.post(reverse("asset-initiate-upload"), payload, format="json")

    def _put_pending(self, asset, body, content_type="image/png"):
        self.s3.put_object(Bucket=self.bucket, Key=asset.pending_key, Body=body, ContentType=content_type)

    def _complete(self, asset, user=None):
        self.client.force_authenticate(user=user or self.user)
        return self.client.post(reverse("asset-complete-upload", kwargs={"asset_id": asset.id}))

    def _exists(self, key):
        return self.s3.list_objects_v2(Bucket=self.bucket, Prefix=key)["KeyCount"] > 0

    # --- initiate ------------------------------------------------------------

    def test_initiate_returns_a_presigned_put_url_for_a_pending_key(self):
        response = self._initiate()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["upload_method"], "PUT")
        self.assertIn("X-Amz-Signature", response.data["upload_url"])
        asset = Asset.objects.get(id=response.data["asset_id"])
        self.assertEqual(asset.status, Asset.Status.INITIATED)
        self.assertTrue(asset.pending_key.startswith("assets-pending/job_chat_attachment/"))

    def test_active_content_types_are_rejected_for_public_uploads(self):
        for filename, content_type in (("page.html", "text/html"), ("logo.svg", "image/svg+xml")):
            with self.subTest(content_type):
                response = self._initiate(kind="generic_upload", filename=filename, content_type=content_type)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("content_type", response.data)

    def test_clients_cannot_choose_privileged_kinds(self):
        for kind in ("legal_document", "announcement_image"):
            with self.subTest(kind):
                response = self._initiate(kind=kind, filename="doc.pdf", content_type="application/pdf")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("kind", response.data)

    def test_staff_can_upload_legal_documents(self):
        response = self._initiate(
            user=self.staff, kind="legal_document", filename="terms.pdf", content_type="application/pdf"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_extension_must_match_the_declared_content_type(self):
        response = self._initiate(filename="photo.html")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_size_limit_is_enforced_before_issuing_a_url(self):
        response = self._initiate(size_bytes=settings.JOB_CHAT_ATTACHMENT_MAX_BYTES + 1)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Asset.objects.count(), 0)

    # --- complete ------------------------------------------------------------

    def test_complete_moves_a_valid_upload_to_its_final_key(self):
        asset = Asset.objects.get(id=self._initiate().data["asset_id"])
        pending_key = asset.pending_key
        self._put_pending(asset, png_bytes())

        response = self._complete(asset)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.CONFIRMED)
        self.assertTrue(self._exists(asset.key))
        self.assertFalse(self._exists(pending_key))

    def test_content_that_is_not_what_was_declared_is_rejected_and_deleted(self):
        body = b"<script>alert(1)</script>".ljust(len(png_bytes()), b" ")
        asset = Asset.objects.get(id=self._initiate().data["asset_id"])
        self._put_pending(asset, body)

        response = self._complete(asset)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"file": "Uploaded file is not a valid image/png file."})
        self.assertFalse(self._exists(asset.pending_key))
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.INITIATED)

    def test_size_mismatch_is_rejected(self):
        asset = Asset.objects.get(id=self._initiate().data["asset_id"])
        self._put_pending(asset, png_bytes() + b"extra")

        self.assertEqual(self._complete(asset).status_code, status.HTTP_400_BAD_REQUEST)

    def test_completing_before_uploading_is_rejected(self):
        asset = Asset.objects.get(id=self._initiate().data["asset_id"])

        response = self._complete(asset)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_the_owner_can_complete_an_upload(self):
        asset = Asset.objects.get(id=self._initiate().data["asset_id"])
        self._put_pending(asset, png_bytes())

        response = self._complete(asset, user=self.other_user)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.INITIATED)

    def test_an_upload_cannot_be_confirmed_twice(self):
        asset = Asset.objects.get(id=self._initiate().data["asset_id"])
        self._put_pending(asset, png_bytes())
        self._complete(asset)

        response = self._complete(asset)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
