from rest_framework import serializers

from ..models import Category, ServiceCatalog


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
