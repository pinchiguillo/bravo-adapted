import uuid

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import Avg, DecimalField, Q, Value


class OrganizationQuerySet(models.QuerySet):
    def with_rating(self):
        if not apps.is_installed("apps.jobs"):
            return self.annotate(
                calculated_rating=Value(
                    None,
                    output_field=DecimalField(max_digits=3, decimal_places=2, null=True),
                )
            )
        return self.annotate(
            calculated_rating=Avg(
                "announcements__jobs__organization_rating",
                filter=Q(
                    announcements__jobs__status="completed",
                    announcements__jobs__organization_rating__isnull=False,
                ),
            )
        )


class Organization(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization",
    )
    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=64)
    billing_email = models.EmailField()
    billing_address = models.CharField(max_length=255)
    billing_city = models.CharField(max_length=120)
    billing_country = models.CharField(max_length=2)
    billing_postal_code = models.CharField(max_length=20)
    verification_level = models.PositiveIntegerField(default=0)
    is_approved = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def validation_bypassed(cls):
        return settings.BYPASS_ORGANIZATION_VALIDATION

    @classmethod
    def validated_filter_kwargs(cls, prefix=""):
        if cls.validation_bypassed():
            return {}
        return {f"{prefix}is_approved": True}

    @property
    def is_validated(self):
        return self.validation_bypassed() or self.is_approved

    def get_rating(self):
        if not apps.is_installed("apps.jobs"):
            return None
        return self.announcements.filter(
            jobs__status="completed",
            jobs__organization_rating__isnull=False,
        ).aggregate(rating=Avg("jobs__organization_rating"))["rating"]
