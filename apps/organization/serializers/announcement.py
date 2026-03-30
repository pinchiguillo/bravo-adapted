from django.db.models import Min
from rest_framework import serializers

from ..models import Announcement, Category, Service
from .service import ServiceSerializer


class AnnouncementSerializer(serializers.ModelSerializer):
    HARDCODED_IMAGE_URL = "https://cdn.bravo.example.com/IMG_1715.JPEG"
    HARDCODED_IMAGE_COUNT = 4

    organization = serializers.UUIDField(source="organization.uuid", read_only=True)
    category = serializers.SlugRelatedField(queryset=Category.objects.all(), slug_field="uuid")
    images = serializers.SerializerMethodField()
    lowest_price = serializers.SerializerMethodField()
    services = serializers.SlugRelatedField(
        many=True,
        queryset=Service.objects.select_related("organization", "service_catalog"),
        slug_field="uuid",
        required=False,
    )

    class Meta:
        model = Announcement
        fields = (
            "uuid",
            "organization",
            "category",
            "images",
            "lowest_price",
            "services",
            "name",
            "location",
            "announcement",
            "status",
            "description",
            "free_text",
            "latitude",
            "longitude",
            "view_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "organization",
            "view_count",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError(
                {"coordinates": "Latitude and longitude must both be provided or both be null."}
            )
        return attrs

    def validate_services(self, value):
        organization = self.context.get("organization")
        if organization is None:
            return value
        invalid_services = [
            service for service in value if service.organization_id != organization.id
        ]
        if invalid_services:
            raise serializers.ValidationError("Services must belong to the organization in the URL.")
        return value

    def get_lowest_price(self, obj):
        lowest_price = obj.services.aggregate(
            min_amount=Min("subservices__price_table__amount")
        )["min_amount"]
        if lowest_price is None:
            return None
        return f"{lowest_price:.2f}"

    def get_images(self, obj):
        return [self.HARDCODED_IMAGE_URL] * self.HARDCODED_IMAGE_COUNT

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["category"] = str(instance.category.uuid)
        data["services"] = ServiceSerializer(instance.services.all(), many=True).data
        return data
