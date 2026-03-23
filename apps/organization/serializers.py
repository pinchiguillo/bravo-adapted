from rest_framework import serializers

from .models import (
    Announcement,
    Category,
    Organization,
    OrganizationJob,
    Service,
    ServicePrice,
    Subservice,
)


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
            "is_approved",
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


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("uuid", "name", "description")
        read_only_fields = ("uuid",)


class OrganizationJobSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="organization.uuid", read_only=True)

    class Meta:
        model = OrganizationJob
        fields = (
            "uuid",
            "organization",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "organization", "created_at", "updated_at")


class AnnouncementSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="organization.uuid", read_only=True)
    category = serializers.SlugRelatedField(queryset=Category.objects.all(), slug_field="uuid")
    services = serializers.SlugRelatedField(
        many=True,
        queryset=Service.objects.select_related("job", "job__organization"),
        slug_field="uuid",
        required=False,
    )

    class Meta:
        model = Announcement
        fields = (
            "uuid",
            "organization",
            "category",
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
            service for service in value if service.job.organization_id != organization.id
        ]
        if invalid_services:
            raise serializers.ValidationError("Services must belong to the organization in the URL.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["category"] = str(instance.category.uuid)
        data["services"] = [str(service_uuid) for service_uuid in data["services"]]
        return data


class ServiceSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="job.organization.uuid", read_only=True)
    job = serializers.UUIDField(source="job.uuid", read_only=True)
    category = serializers.SlugRelatedField(queryset=Category.objects.all(), slug_field="uuid")

    class Meta:
        model = Service
        fields = (
            "uuid",
            "organization",
            "job",
            "category",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "organization", "job", "created_at", "updated_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["category"] = str(instance.category.uuid)
        return data


class ServicePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = (
            "uuid",
            "amount",
            "currency",
            "charging_type",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SubserviceSerializer(serializers.ModelSerializer):
    service = serializers.SlugRelatedField(
        queryset=Service.objects.select_related("job", "job__organization"),
        slug_field="uuid",
    )
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
