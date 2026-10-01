from datetime import date

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.money import Currency, CurrencyField

from ..models import Announcement, ServiceCatalog, ServicePrice, Subservice
from .catalog import CatalogReferenceField, CategorySerializer


class SubservicePriceWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating service prices during subservice creation."""

    currency = CurrencyField(required=False, default=Currency.EUR)

    class Meta:
        model = ServicePrice
        fields = ("amount", "currency", "charging_type", "effective_from", "effective_to")

    def validate_effective_to(self, value):
        if value is not None and value < date.today():
            raise serializers.ValidationError("effective_to must be today or in the future.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("effective_to") and attrs.get("effective_to") < attrs.get("effective_from"):
            raise serializers.ValidationError(
                {"effective_to": "effective_to must be after or equal to effective_from."}
            )
        return attrs


class ServicePriceSerializer(serializers.ModelSerializer):
    subservice = serializers.SlugRelatedField(
        queryset=Subservice.objects.select_related("announcement", "announcement__organization"),
        slug_field="uuid",
        required=False,
    )
    # No default: on create the model default (EUR) applies, and a PUT that
    # omits the currency must keep the stored one.
    currency = CurrencyField(required=False)

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
