import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.money import Currency


class OrganizationPricing(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.OneToOneField(
        "organization.Organization",
        on_delete=models.CASCADE,
        related_name="pricing",
    )
    plan_tier = models.ForeignKey(
        "organization.PlanTierCatalog",
        on_delete=models.PROTECT,
        related_name="organization_pricings",
    )
    monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EUR)
    feature_flags = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization_id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(commission_rate__gte=0)
                & models.Q(commission_rate__lte=100),
                name="organization_pricing_commission_rate_between_0_and_100",
            ),
            models.CheckConstraint(
                condition=models.Q(monthly_price__gte=0),
                name="organization_pricing_monthly_price_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.organization_id}:{self.plan_tier_id}"
