import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Job(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"
        INACTIVE = "inactive", "Inactive"

    # Status changes each participant may make; staff can set any status.
    # PENDING -> ACTIVE happens when the requester accepts a price proposal
    # (job_chat.services.set_proposal_status).
    REQUESTER_TRANSITIONS = {
        Status.PENDING: {Status.INACTIVE},
        Status.ACTIVE: {Status.COMPLETED, Status.INACTIVE},
    }
    PROVIDER_TRANSITIONS = {
        Status.PENDING: {Status.REJECTED},
        Status.ACTIVE: {Status.COMPLETED},
    }

    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    announcement = models.ForeignKey(
        "organization.Announcement",
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    plan_price = models.ForeignKey(
        "organization.ServicePrice",
        on_delete=models.PROTECT,
        related_name="jobs",
        null=True,
        blank=True,
    )
    organization_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("5"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["announcement", "-created_at"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(organization_rating__isnull=True)
                | models.Q(organization_rating__gte=1, organization_rating__lte=5),
                name="job_rating_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"Job {self.uuid} - {self.user.username} - {self.status}"

    def is_requester(self, user):
        return bool(user and user.is_authenticated and self.user_id == user.id)

    def is_provider(self, user):
        return bool(
            user
            and user.is_authenticated
            and self.announcement.organization.user_id == user.id
        )

    def can_access_as_participant(self, user):
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_staff
                or self.is_requester(user)
                or self.is_provider(user)
            )
        )
