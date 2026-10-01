import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Asset(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PROTECTED = "protected", "Protected"
        PRIVATE = "private", "Private"

    class Kind(models.TextChoices):
        ANNOUNCEMENT_IMAGE = "announcement_image", "Announcement image"
        JOB_CHAT_ATTACHMENT = "job_chat_attachment", "Job chat attachment"
        LEGAL_DOCUMENT = "legal_document", "Legal document"
        GENERIC_UPLOAD = "generic_upload", "Generic upload"

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        UPLOADED = "uploaded", "Uploaded"
        CONFIRMED = "confirmed", "Confirmed"
        ATTACHED = "attached", "Attached"
        ORPHAN = "orphan", "Orphan"
        REJECTED = "rejected", "Rejected"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assets",
    )

    visibility = models.CharField(max_length=20, choices=Visibility.choices)
    kind = models.CharField(max_length=40, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIATED)

    # pending_key: temp S3 location during upload; cleared after confirmation
    pending_key = models.CharField(max_length=1024, blank=True)
    # key: final S3 location; set at initiation, file only moves there at confirmation
    key = models.CharField(max_length=1024, unique=True)

    original_filename = models.CharField(max_length=255)
    content_type_client = models.CharField(max_length=120, blank=True)
    size_client = models.BigIntegerField(null=True, blank=True)
    content_type_detected = models.CharField(max_length=120, blank=True)
    size_actual = models.BigIntegerField(null=True, blank=True)

    is_temporary = models.BooleanField(default=True)
    draft_token = models.CharField(max_length=64, blank=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Optional generic binding to a business entity (set after attachment)
    content_type_ref = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    object_id = models.CharField(max_length=64, blank=True)
    content_object = GenericForeignKey("content_type_ref", "object_id")

    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assets_asset"
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["kind", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"Asset({self.kind}/{self.status}/{self.id})"
