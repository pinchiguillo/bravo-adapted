from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import Announcement, ServiceCatalog, ServicePrice, Subservice
from .catalog import CatalogReferenceField, CategorySerializer


class ServicePriceSerializer(serializers.ModelSerializer):
    subservice = serializers.SlugRelatedField(
        queryset=Subservice.objects.select_related("announcement", "announcement__organization"),
        slug_field="uuid",
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["subservice"] = str(instance.subservice.uuid)
        return data


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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["subservice"] = str(instance.subservice.uuid)
        return data


class SubserviceSerializer(serializers.ModelSerializer):
    announcement = serializers.SlugRelatedField(
        queryset=Announcement.objects.select_related("organization"),
        slug_field="uuid",
        required=False,
    )
    service_catalog = CatalogReferenceField(
        queryset=ServiceCatalog.objects.select_related("category"),
        slug_field="uuid",
    )
    service_prices = PublicServicePriceSerializer(source="price_table", many=True, read_only=True)

    class Meta:
        model = Subservice
        fields = (
            "uuid",
            "announcement",
            "service_catalog",
            "service_prices",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")

class ServiceSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    subservices = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCatalog
        fields = (
            "uuid",
            "category",
            "subservices",
            "name",
            "description",
        )
        read_only_fields = fields

    @extend_schema_field(SubserviceSerializer(many=True))
    def get_subservices(self, obj):
        subservices = getattr(obj, "_announcement_subservices", obj.subservices.all())
        return SubserviceSerializer(subservices, many=True, context=self.context).data
