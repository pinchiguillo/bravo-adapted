from rest_framework import serializers

from .models import (
    Announcement,
    Category,
    Organization,
    Service,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)


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


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("uuid", "name", "description")
        read_only_fields = ("uuid",)


class ServiceCatalogSerializer(serializers.ModelSerializer):
    category = serializers.UUIDField(source="category.uuid", read_only=True)

    class Meta:
        model = ServiceCatalog
        fields = (
            "uuid",
            "category",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AnnouncementSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="organization.uuid", read_only=True)
    category = serializers.SlugRelatedField(queryset=Category.objects.all(), slug_field="uuid")
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["category"] = str(instance.category.uuid)
        data["services"] = ServiceSerializer(instance.services.all(), many=True).data
        return data


class ServiceSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="organization.uuid", read_only=True)
    service_catalog = serializers.SlugRelatedField(
        queryset=ServiceCatalog.objects.select_related("category"),
        slug_field="uuid",
    )
    category = serializers.SlugRelatedField(queryset=Category.objects.all(), slug_field="uuid")
    subservices = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "uuid",
            "organization",
            "service_catalog",
            "category",
            "subservices",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "organization", "created_at", "updated_at")

    def get_subservices(self, obj):
        return SubserviceSerializer(obj.subservices.all(), many=True).data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        service_catalog = attrs.get("service_catalog", getattr(self.instance, "service_catalog", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        if service_catalog is not None and category is not None and service_catalog.category_id != category.id:
            raise serializers.ValidationError(
                {"category": "Category must match the selected service catalog."}
            )
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["category"] = str(instance.category.uuid)
        data["service_catalog"] = str(instance.service_catalog.uuid)
        return data


class ServicePriceSerializer(serializers.ModelSerializer):
    subservice = serializers.SlugRelatedField(
        queryset=Subservice.objects.select_related("service", "service__organization"),
        slug_field="uuid",
        write_only=True,
        required=False,
    )

    class Meta:
        model = ServicePrice
        fields = (
            "uuid",
            "subservice",
            "amount",
            "currency",
            "charging_type",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")


class PublicServicePriceSerializer(serializers.ModelSerializer):
    subservice = serializers.UUIDField(source="subservice.uuid", read_only=True)

    class Meta:
        model = ServicePrice
        fields = (
            "uuid",
            "subservice",
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
        queryset=Service.objects.select_related("organization", "service_catalog"),
        slug_field="uuid",
    )
    service_prices = PublicServicePriceSerializer(source="price_table", many=True, read_only=True)

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["service"] = str(instance.service.uuid)
        return data
