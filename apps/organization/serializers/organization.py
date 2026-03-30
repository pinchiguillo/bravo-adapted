from rest_framework import serializers

from ..models import Organization


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

    class Meta:
        model = Organization
        fields = (
            "uuid",
            "name",
            "verification_level",
            "is_approved",
            "rating",
        )
        read_only_fields = ("uuid",)


class OrganizationSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
    is_approved = serializers.BooleanField(source="is_validated", read_only=True)

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
