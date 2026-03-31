import uuid

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
