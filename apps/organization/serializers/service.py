from rest_framework import serializers

from ..models import Category, Service, ServiceCatalog, ServicePrice, Subservice


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
        extra_kwargs = {
            "description": {"required": True, "allow_blank": False},
        }

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
