from rest_framework import serializers

from ..models import AllowedCity, Category, ServiceCatalog


class CatalogReferenceField(serializers.SlugRelatedField):
    def to_representation(self, obj):
        return {
            "uuid": str(obj.uuid),
            "name": obj.name,
        }


class AllowedCitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AllowedCity
        fields = ("uuid", "name")
        read_only_fields = ("uuid",)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("uuid", "name")
        read_only_fields = ("uuid",)


class ServiceCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCatalog
        fields = ("uuid", "name")
        read_only_fields = fields
