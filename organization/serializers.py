from rest_framework import serializers

from .models import Category, Organization, Service, ServicePrice, Subservice


class OrganizationPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "uuid",
            "name",
        )
        read_only_fields = ("uuid",)


class OrganizationSerializer(serializers.ModelSerializer):
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
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")


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


class SubserviceSerializer(serializers.ModelSerializer):
    service = serializers.SlugRelatedField(queryset=Service.objects.all(), slug_field="uuid")

    class Meta:
        model = Subservice
        fields = (
            "uuid",
            "service",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")


class ServicePriceSerializer(serializers.ModelSerializer):
    service = serializers.SlugRelatedField(queryset=Service.objects.all(), slug_field="uuid")

    class Meta:
        model = ServicePrice
        fields = (
            "uuid",
            "service",
            "amount",
            "currency",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")
