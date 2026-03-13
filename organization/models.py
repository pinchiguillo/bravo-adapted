import uuid

from django.conf import settings
from django.db import models
from django.db.models import Avg, Q


class OrganizationQuerySet(models.QuerySet):
    def with_rating(self):
        return self.annotate(
            calculated_rating=Avg(
                "jobs__organization_rating",
                filter=Q(
                    jobs__status="completed",
                    jobs__organization_rating__isnull=False,
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

    def get_rating(self):
        return self.jobs.filter(
            status="completed",
            organization_rating__isnull=False,
        ).aggregate(rating=Avg("organization_rating"))["rating"]


class Service(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="services"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="unique_organization_service_name"
            )
        ]
        ordering = ["organization_id", "name"]

    def __str__(self):
        return f"{self.organization_id}:{self.name}"


class Subservice(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="subservices")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service", "name"], name="unique_service_subservice_name"
            )
        ]
        ordering = ["service_id", "name"]

    def __str__(self):
        return f"{self.service_id}:{self.name}"


class ServicePrice(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    subservice = models.ForeignKey(
        Subservice,
        on_delete=models.CASCADE,
        related_name="price_table",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    effective_from = models.DateField()
    effective_to = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subservice", "currency", "effective_from"],
                name="unique_subservice_price_effective_from",
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=models.F("effective_from")),
                name="service_price_effective_to_after_start",
            ),
        ]
        ordering = ["subservice_id", "-effective_from", "-id"]

    def __str__(self):
        return f"{self.subservice_id}:{self.currency}:{self.amount}"


class Category(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
