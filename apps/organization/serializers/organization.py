from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import Organization
from .catalog import PlanTierCatalogSerializer


class OrganizationRatingMixin(serializers.Serializer):
    rating = serializers.SerializerMethodField()

    def get_rating(self, obj) -> str | None:
        rating = getattr(obj, "calculated_rating", None)
        if rating is None:
            rating = obj.get_rating()
        if rating is None:
            return None
        return f"{rating:.2f}"


class OrganizationPublicSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
    is_approved = serializers.BooleanField(source="is_validated", read_only=True)
    plan_tier = serializers.SerializerMethodField()

    @extend_schema_field(PlanTierCatalogSerializer(allow_null=True))
    def get_plan_tier(self, obj):
        pricing = getattr(obj, "pricing", None)
        if pricing is None or pricing.plan_tier_id is None:
            return None
        return PlanTierCatalogSerializer(pricing.plan_tier).data

    class Meta:
        model = Organization
        fields = (
            "uuid",
            "name",
            "verification_level",
            "is_approved",
            "plan_tier",
            "rating",
        )
        read_only_fields = ("uuid",)


class OrganizationSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
    is_approved = serializers.BooleanField(source="is_validated", read_only=True)
    plan_tier = serializers.SerializerMethodField()

    @extend_schema_field(PlanTierCatalogSerializer(allow_null=True))
    def get_plan_tier(self, obj):
        pricing = getattr(obj, "pricing", None)
        if pricing is None or pricing.plan_tier_id is None:
            return None
        return PlanTierCatalogSerializer(pricing.plan_tier).data

    class Meta:
        model = Organization
        fields = (
            "uuid",
            "name",
            "legal_name",
            "tax_id",
            "billing_email",
            "billing_address",
            "billing_city",
            "billing_country",
            "billing_postal_code",
            "verification_level",
            "is_approved",
            "plan_tier",
            "rating",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "verification_level",
            "is_approved",
            "rating",
            "created_at",
            "updated_at",
        )
