from rest_framework import serializers

from .models import Category, Organization, Service, ServicePrice, Subservice


class OrganizationRatingMixin(serializers.Serializer):
    rating = serializers.SerializerMethodField()

    def get_rating(self, obj):
        rating = getattr(obj, "calculated_rating", None)
        if rating is None:
            rating = obj.get_rating()
        if rating is None:
            return None
        return f"{rating:.2f}"


class OrganizationPublicSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "uuid",
            "name",
            "verification_level",
            "rating",
        )
        read_only_fields = ("uuid",)


class OrganizationSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
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
            "rating",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "verification_level", "rating", "created_at", "updated_at")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("uuid", "name")
        read_only_fields = ("uuid",)


class ServiceSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="organization.uuid", read_only=True)

    class Meta:
        model = Service
        fields = (
            "uuid",
            "organization",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "organization", "created_at", "updated_at")


class ServicePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = (
            "uuid",
            "amount",
            "currency",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SubserviceSerializer(serializers.ModelSerializer):
    service = serializers.SlugRelatedField(queryset=Service.objects.all(), slug_field="uuid")
    service_prices = ServicePriceSerializer(source="price_table", many=True, read_only=True)

    class Meta:
        model = Subservice
        fields = (
            "uuid",
            "service",
            "service_prices",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")
