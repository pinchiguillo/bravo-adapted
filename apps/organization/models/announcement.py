import uuid

from django.conf import settings
from django.db import models


class Announcement(models.Model):
    class Status(models.TextChoices):
        CLOSED = "closed", "Closed"
        SUSPENDED = "suspended", "Suspended"
        ACTIVE = "active", "Active"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        "organization.Organization",
        on_delete=models.CASCADE,
        related_name="announcements",
    )
    category = models.ForeignKey(
        "organization.Category",
        on_delete=models.PROTECT,
        related_name="announcements",
    )
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    announcement = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    description = models.TextField(blank=True)
    free_text = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    view_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization_id", "-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(latitude__isnull=True, longitude__isnull=True)
                    | models.Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="announcement_coordinates_all_or_none",
            )
        ]

    def __str__(self):
        return f"{self.organization_id}:{self.name}"


class AnnouncementImage(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    announcement = models.ForeignKey(
        "organization.Announcement",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="organization-announcements/%Y/%m/%d/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.announcement_id}:image:{self.id}"


class AnnouncementReview(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    announcement = models.OneToOneField(
        "organization.Announcement",
        on_delete=models.CASCADE,
        related_name="review",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["announcement_id"]

    def __str__(self):
        return f"{self.announcement_id}:review"


class AnnouncementStatusChange(models.Model):
    """Tracks status changes of announcements, including suspension/activation reasons."""

    class ChangeReason(models.TextChoices):
        ADMIN_DECISION = "admin_decision", "Admin Decision"
        POLICY_VIOLATION = "policy_violation", "Policy Violation"
        CONTENT_REVIEW = "content_review", "Content Review"
        USER_REQUEST = "user_request", "User Request"
        TECHNICAL_ISSUE = "technical_issue", "Technical Issue"
        OTHER = "other", "Other"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    announcement = models.ForeignKey(
        "organization.Announcement",
        on_delete=models.CASCADE,
        related_name="status_changes",
    )
    from_status = models.CharField(
        max_length=20,
        choices=Announcement.Status.choices,
    )
    to_status = models.CharField(
        max_length=20,
        choices=Announcement.Status.choices,
    )
    reason = models.CharField(
        max_length=50,
        choices=ChangeReason.choices,
        default=ChangeReason.ADMIN_DECISION,
    )
    reason_text = models.TextField(
        blank=True,
        help_text="Detailed explanation for the status change",
    )
    changed_by = models.CharField(
        max_length=255,
        default="admin",
        help_text="User or system that performed the change",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "announcement_id"]
        indexes = [
            models.Index(fields=["announcement", "-created_at"]),
            models.Index(fields=["to_status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.announcement.uuid}: {self.from_status} → {self.to_status}"


class AnnouncementFavorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_favorites",
    )
    announcement = models.ForeignKey(
        "organization.Announcement",
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "announcement")
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user_id}:favorite:{self.announcement_id}"
