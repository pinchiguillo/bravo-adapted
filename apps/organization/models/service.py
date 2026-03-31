import uuid

from django.db import models


class Subservice(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    announcement = models.ForeignKey(
        "organization.Announcement",
        on_delete=models.CASCADE,
        related_name="subservices",
    )
    service_catalog = models.ForeignKey(
        "organization.ServiceCatalog",
        on_delete=models.PROTECT,
        related_name="subservices",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "service_catalog", "name"],
                name="unique_announcement_service_catalog_subservice_name",
            )
        ]
        ordering = ["announcement_id", "service_catalog_id", "name"]

    def __str__(self):
        return f"{self.announcement_id}:{self.service_catalog_id}:{self.name}"


class ServicePrice(models.Model):
    class ChargingType(models.TextChoices):
        PER_DAY = "per_day", "Per day"
        PER_HOUR = "per_hour", "Per hour"
        PER_SQUARE_METER = "per_square_meter", "Per square meter"
        PER_PROJECT = "per_project", "Per project"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    subservice = models.ForeignKey(
        "organization.Subservice",
        on_delete=models.CASCADE,
        related_name="price_table",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    charging_type = models.CharField(
        max_length=20,
        choices=ChargingType.choices,
        default=ChargingType.PER_PROJECT,
    )
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
