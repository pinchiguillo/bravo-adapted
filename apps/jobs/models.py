import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.organization.models import Announcement, ServicePrice


class Job(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    plan_price = models.ForeignKey(
        ServicePrice,
        on_delete=models.PROTECT,
        related_name="jobs",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    organization_rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.uuid}:{self.status}"

    @property
    def organization(self):
        return self.announcement.organization

    @property
    def organization_id(self):
        return self.announcement.organization_id
