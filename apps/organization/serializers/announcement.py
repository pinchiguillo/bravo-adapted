import mimetypes
import os
from collections import OrderedDict
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import Min
from django.urls import reverse
from django.utils.encoding import filepath_to_uri
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import Announcement, AnnouncementImage, Category
from .catalog import CatalogReferenceField
from .service import ServiceSerializer


class AnnouncementImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(write_only=True)
    image_url = serializers.SerializerMethodField()
    base64_url = serializers.SerializerMethodField()
    filename = serializers.SerializerMethodField()

    class Meta:
        model = AnnouncementImage
        fields = ("uuid", "image", "image_url", "base64_url", "filename", "created_at")
        read_only_fields = ("uuid", "image_url", "base64_url", "filename", "created_at")

    def validate_image(self, image):
        allowed_content_types = set(
            getattr(settings, "ORGANIZATION_ANNOUNCEMENT_IMAGE_ALLOWED_CONTENT_TYPES", [])
        )
        content_type = getattr(image, "content_type", "")
        detected_content_type = self._detect_content_type(image)

        if allowed_content_types and detected_content_type not in allowed_content_types:
            raise serializers.ValidationError("Unsupported file type.")
        if content_type and detected_content_type != content_type:
            raise serializers.ValidationError("File content type does not match file contents.")

        max_bytes = getattr(settings, "ORGANIZATION_ANNOUNCEMENT_IMAGE_MAX_BYTES", 5 * 1024 * 1024)
        if image.size > max_bytes:
            raise serializers.ValidationError(
                f"File exceeds the maximum allowed size of {max_bytes} bytes."
            )
        return image

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_image_url(self, obj) -> str | None:
        try:
            url = obj.image.url
        except ValueError:
            return None

        file_name = getattr(obj.image, "name", "")
        media_url = getattr(settings, "MEDIA_URL", "")
        if file_name and media_url.startswith("/"):
            parsed_url = urlsplit(url)
            public_url = f"{media_url.rstrip('/')}/{filepath_to_uri(file_name).lstrip('/')}"
            if parsed_url.query:
                public_url = f"{public_url}?{parsed_url.query}"
            url = public_url

        request = self.context.get("request")
        if request is None or not url.startswith("/"):
            return url
        return request.build_absolute_uri(url)

    @extend_schema_field(serializers.CharField())
    def get_filename(self, obj) -> str:
        return os.path.basename(obj.image.name)

    @extend_schema_field(serializers.URLField())
    def get_base64_url(self, obj) -> str:
        request = self.context.get("request")
        organization = self.context.get("organization")

        if organization is None:
            url = reverse(
                "public-announcement-image-base64",
                kwargs={"uuid": obj.announcement.uuid, "image_uuid": obj.uuid},
            )
        else:
            url = reverse(
                "organization-announcement-image-base64",
                kwargs={
                    "organization_uuid": organization.uuid,
                    "uuid": obj.announcement.uuid,
                    "image_uuid": obj.uuid,
                },
            )

        if request is None:
            return url
        return request.build_absolute_uri(url)

    def _detect_content_type(self, image):
        image.seek(0)
        sample = image.read(512)
        image.seek(0)

        if sample.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if sample.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        return "application/octet-stream"


class AnnouncementImageBase64Serializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    filename = serializers.CharField(read_only=True)
    content_type = serializers.CharField(read_only=True)
    data = serializers.CharField(read_only=True)

    def to_representation(self, instance):
        file_name = getattr(instance.image, "name", "")
        content_type, _ = mimetypes.guess_type(file_name)
        return {
            "uuid": str(instance.uuid),
            "filename": os.path.basename(file_name),
            "content_type": content_type or "application/octet-stream",
            "data": self.context["encoded_data"],
        }


class AnnouncementSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="organization.uuid", read_only=True)
    title = serializers.CharField(source="announcement")
    category = CatalogReferenceField(queryset=Category.objects.all(), slug_field="uuid")
    images = AnnouncementImageSerializer(many=True, read_only=True)
    lowest_price = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()

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
            "title",
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
        extra_kwargs = {
            "description": {"required": True, "allow_blank": False},
            "free_text": {"required": True, "allow_blank": False},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError(
                {"coordinates": "Latitude and longitude must both be provided or both be null."}
            )
        return attrs

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_lowest_price(self, obj) -> str | None:
        lowest_price = obj.subservices.aggregate(min_amount=Min("price_table__amount"))["min_amount"]
        if lowest_price is None:
            return None
        return f"{lowest_price:.2f}"

    @extend_schema_field(ServiceSerializer(many=True))
    def get_services(self, obj):
        grouped_catalogs = OrderedDict()
        subservices = obj.subservices.select_related("service_catalog", "service_catalog__category").all()

        for subservice in subservices:
            catalog = subservice.service_catalog
            if catalog.pk not in grouped_catalogs:
                grouped_catalogs[catalog.pk] = catalog
                grouped_catalogs[catalog.pk]._announcement_subservices = []
            grouped_catalogs[catalog.pk]._announcement_subservices.append(subservice)

        return ServiceSerializer(
            grouped_catalogs.values(),
            many=True,
            context=self.context,
        ).data
