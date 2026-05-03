import mimetypes
import os
import uuid
from collections import OrderedDict

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Min
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.assets.services import (
    build_public_media_url,
    cleanup_expired_pending_files,
    generate_presigned_upload_url,
    move_pending_to_confirmed,
)

from ..models import (
    Announcement,
    AnnouncementFavorite,
    AnnouncementImage,
    AnnouncementStatusChange,
    Category,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)
from .catalog import CatalogReferenceField
from .service import ServiceSerializer, SubservicePriceWriteSerializer


def build_announcement_image_upload_token(payload):
    return signing.dumps(payload, salt="organization.announcement_image_upload")


def load_announcement_image_upload_token(token, *, max_age):
    return signing.loads(
        token,
        salt="organization.announcement_image_upload",
        max_age=max_age,
    )


def build_pending_announcement_image_name(announcement, filename):
    ext = os.path.splitext(filename)[1].lower()
    now = timezone.now()
    return (
        f"organization-announcements-pending/"
        f"{announcement.uuid}/{now:%Y/%m/%d}/{uuid.uuid4().hex}{ext}"
    )


def build_final_announcement_image_name(image_instance, filename):
    field = AnnouncementImage._meta.get_field("image")
    return field.generate_filename(image_instance, filename)


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
        return build_public_media_url(
            file_name,
            request=self.context.get("request"),
            signed_url=url,
        )

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


class AnnouncementImageUploadRequestSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=100)
    size_bytes = serializers.IntegerField(min_value=1)

    def validate_filename(self, value):
        filename = os.path.basename(str(value).strip())
        if not filename:
            raise serializers.ValidationError("Filename is required.")
        return filename

    def validate_content_type(self, value):
        content_type = str(value).strip().lower()
        allowed_content_types = set(
            getattr(settings, "ORGANIZATION_ANNOUNCEMENT_IMAGE_ALLOWED_CONTENT_TYPES", [])
        )
        if allowed_content_types and content_type not in allowed_content_types:
            raise serializers.ValidationError("Unsupported file type.")
        return content_type

    def validate_size_bytes(self, value):
        max_bytes = getattr(settings, "ORGANIZATION_ANNOUNCEMENT_IMAGE_MAX_BYTES", 5 * 1024 * 1024)
        if value > max_bytes:
            raise serializers.ValidationError(
                f"File exceeds the maximum allowed size of {max_bytes} bytes."
            )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        filename = attrs["filename"]
        content_type = attrs["content_type"]
        detected_content_type, _ = mimetypes.guess_type(filename)
        if detected_content_type and detected_content_type != content_type:
            raise serializers.ValidationError(
                {"content_type": "File content type does not match filename extension."}
            )
        return attrs

    def create(self, validated_data):
        announcement = self.context["announcement"]
        request = self.context.get("request")
        ttl_seconds = getattr(
            settings,
            "ORGANIZATION_ANNOUNCEMENT_IMAGE_UPLOAD_URL_TTL_SECONDS",
            300,
        )
        field = AnnouncementImage._meta.get_field("image")
        storage = field.storage
        if not hasattr(storage, "bucket_name") or not hasattr(storage, "connection"):
            raise serializers.ValidationError("Direct upload is not supported by the configured storage.")

        cleanup_expired_pending_files(
            storage,
            prefix="organization-announcements-pending/",
            max_age_seconds=settings.ORGANIZATION_ANNOUNCEMENT_IMAGE_PENDING_MAX_AGE_SECONDS,
        )
        pending_name = build_pending_announcement_image_name(announcement, validated_data["filename"])
        final_name = storage.get_available_name(
            build_final_announcement_image_name(
                AnnouncementImage(announcement=announcement),
                validated_data["filename"],
            )
        )

        signed_upload_url = generate_presigned_upload_url(
            storage,
            key=pending_name,
            content_type=validated_data["content_type"],
            ttl_seconds=ttl_seconds,
        )
        upload_token = build_announcement_image_upload_token(
            {
                "announcement_uuid": str(announcement.uuid),
                "organization_uuid": str(announcement.organization.uuid),
                "pending_file_name": pending_name,
                "final_file_name": final_name,
                "filename": validated_data["filename"],
                "content_type": validated_data["content_type"],
                "size_bytes": validated_data["size_bytes"],
            }
        )
        complete_url = reverse(
            "organization-announcement-image-complete",
            kwargs={
                "organization_uuid": announcement.organization.uuid,
                "uuid": announcement.uuid,
            },
        )

        return {
            "upload_url": build_public_media_url(
                pending_name,
                request=request,
                signed_url=signed_upload_url,
            ),
            "upload_method": "PUT",
            "upload_headers": {
                "Content-Type": validated_data["content_type"],
            },
            "expires_in": ttl_seconds,
            "upload_token": upload_token,
            "complete_url": request.build_absolute_uri(complete_url) if request is not None else complete_url,
        }


class AnnouncementImageUploadTargetSerializer(serializers.Serializer):
    upload_url = serializers.URLField(read_only=True)
    upload_method = serializers.CharField(read_only=True)
    upload_headers = serializers.DictField(child=serializers.CharField(), read_only=True)
    expires_in = serializers.IntegerField(read_only=True)
    upload_token = serializers.CharField(read_only=True)
    complete_url = serializers.URLField(read_only=True)

    def to_representation(self, instance):
        return {
            "upload_url": instance["upload_url"],
            "upload_method": instance["upload_method"],
            "upload_headers": instance["upload_headers"],
            "expires_in": instance["expires_in"],
            "upload_token": instance["upload_token"],
            "complete_url": instance["complete_url"],
        }


class AnnouncementImageUploadCompleteSerializer(serializers.Serializer):
    upload_token = serializers.CharField()

    default_error_messages = {
        "missing_object": "Uploaded file was not found in storage.",
        "mismatched_size": "Uploaded file size does not match the declared size.",
        "mismatched_type": "Uploaded file content type does not match the declared content type.",
    }

    def validate_upload_token(self, value):
        max_age = getattr(
            settings,
            "ORGANIZATION_ANNOUNCEMENT_IMAGE_UPLOAD_URL_TTL_SECONDS",
            300,
        )
        try:
            payload = load_announcement_image_upload_token(value, max_age=max_age)
        except signing.SignatureExpired as exc:
            raise serializers.ValidationError("Upload token has expired.") from exc
        except signing.BadSignature as exc:
            raise serializers.ValidationError("Invalid upload token.") from exc

        announcement = self.context["announcement"]
        if (
            payload.get("announcement_uuid") != str(announcement.uuid)
            or payload.get("organization_uuid") != str(announcement.organization.uuid)
        ):
            raise serializers.ValidationError("Upload token does not belong to this announcement.")

        self.context["upload_payload"] = payload
        return value

    def create(self, validated_data):
        payload = self.context["upload_payload"]
        announcement = self.context["announcement"]
        field = AnnouncementImage._meta.get_field("image")
        storage = field.storage

        move_pending_to_confirmed(
            storage,
            pending_key=payload["pending_file_name"],
            final_key=payload["final_file_name"],
            content_type=payload["content_type"],
            expected_size=payload["size_bytes"],
        )

        image = AnnouncementImage.objects.create(
            announcement=announcement,
            image=payload["final_file_name"],
        )
        return image


class AnnouncementSubserviceWriteSerializer(serializers.ModelSerializer):
    service_catalog = CatalogReferenceField(
        queryset=ServiceCatalog.objects.select_related("category"),
        slug_field="uuid",
    )
    prices = SubservicePriceWriteSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Subservice
        fields = ("service_catalog", "name", "description", "prices")


class AnnouncementSerializer(serializers.ModelSerializer):
    organization = serializers.UUIDField(source="organization.uuid", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    favorite = serializers.SerializerMethodField()
    title = serializers.CharField(source="announcement")
    category = CatalogReferenceField(queryset=Category.objects.all(), slug_field="uuid")
    subservices = AnnouncementSubserviceWriteSerializer(many=True, write_only=True, required=False)
    image_uuids = serializers.SlugRelatedField(
        many=True,
        slug_field="uuid",
        queryset=AnnouncementImage.objects.select_related("announcement"),
        write_only=True,
        required=False,
    )
    images = AnnouncementImageSerializer(many=True, read_only=True)
    lowest_price = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = (
            "uuid",
            "organization",
            "organization_name",
            "favorite",
            "category",
            "subservices",
            "image_uuids",
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
            "organization_name",
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

    def validate_subservices(self, subservices):
        seen_subservices = set()
        for subservice in subservices:
            identifier = (subservice["service_catalog"].pk, subservice["name"].strip().lower())
            if identifier in seen_subservices:
                raise serializers.ValidationError(
                    "Subservices must be unique by service catalog and name."
                )
            seen_subservices.add(identifier)
        return subservices

    def validate_image_uuids(self, images):
        if self.instance is None:
            raise serializers.ValidationError(
                "image_uuids can only be used when updating an existing announcement."
            )

        seen_image_ids = set()
        invalid_images = []
        for image in images:
            if image.uuid in seen_image_ids:
                raise serializers.ValidationError("image_uuids must not contain duplicates.")
            seen_image_ids.add(image.uuid)
            if image.announcement_id != self.instance.id:
                invalid_images.append(str(image.uuid))

        if invalid_images:
            raise serializers.ValidationError(
                f"Images do not belong to this announcement: {', '.join(invalid_images)}"
            )
        return images

    def _create_subservices(self, announcement, subservices):
        for subservice_data in subservices:
            prices_data = subservice_data.pop("prices", [])
            subservice = Subservice.objects.create(announcement=announcement, **subservice_data)
            for price_data in prices_data:
                ServicePrice.objects.create(subservice=subservice, **price_data)

    @transaction.atomic
    def create(self, validated_data):
        subservices = validated_data.pop("subservices", [])
        announcement = super().create(validated_data)
        self._create_subservices(announcement, subservices)
        return announcement

    @transaction.atomic
    def update(self, instance, validated_data):
        subservices = validated_data.pop("subservices", None)
        images = validated_data.pop("image_uuids", None)
        announcement = super().update(instance, validated_data)
        if subservices is not None:
            announcement.subservices.all().delete()
            self._create_subservices(announcement, subservices)
        if images is not None:
            announcement.images.exclude(uuid__in=[image.uuid for image in images]).delete()
        return announcement

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

    @extend_schema_field(serializers.BooleanField())
    def get_favorite(self, obj) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not getattr(user, "is_authenticated", False):
            return False

        prefetched_favorites = getattr(obj, "_favorite_for_request_user", None)
        if prefetched_favorites is not None:
            return bool(prefetched_favorites)

        return AnnouncementFavorite.objects.filter(user=user, announcement=obj).exists()


class AnnouncementStatusChangeSerializer(serializers.ModelSerializer):
    """Serializer for tracking announcement status changes with reasons."""

    class Meta:
        model = AnnouncementStatusChange
        fields = [
            'uuid',
            'announcement',
            'from_status',
            'to_status',
            'reason',
            'reason_text',
            'changed_by',
            'created_at',
        ]
        read_only_fields = ['uuid', 'created_at']


class AnnouncementFavoriteSerializer(serializers.ModelSerializer):
    announcement_uuid = serializers.UUIDField(source='announcement.uuid', read_only=True)

    class Meta:
        model = AnnouncementFavorite
        fields = ('announcement_uuid', 'created_at')
        read_only_fields = ('announcement_uuid', 'created_at')
