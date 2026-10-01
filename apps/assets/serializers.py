import mimetypes
import os
import uuid as uuid_module
from datetime import timedelta

from django.core.files.storage import default_storage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from .models import Asset
from .policies import CLIENT_KINDS, get_kind_rules
from .services import (
    build_asset_key,
    build_pending_asset_key,
    build_public_media_url,
    cleanup_expired_pending_files,
    generate_presigned_upload_url,
    move_pending_to_confirmed,
)


class AssetInitiateUploadSerializer(serializers.Serializer):
    """
    Validate file metadata and issue a presigned S3 PUT URL for direct upload.

    Creates an Asset record in INITIATED status. The client must then:
      1. PUT the file to *upload_url*.
      2. POST to *complete_url* to confirm and move the file to its final location.
    """

    kind = serializers.ChoiceField(choices=Asset.Kind.choices)
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=120)
    size_bytes = serializers.IntegerField(min_value=1)
    draft_token = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def validate_kind(self, value):
        request = self.context.get("request")
        is_staff = bool(request and request.user.is_staff)
        if value not in CLIENT_KINDS and not is_staff:
            raise serializers.ValidationError("This kind of asset cannot be uploaded here.")
        return value

    def validate_filename(self, value):
        filename = os.path.basename(str(value).strip())
        if not filename:
            raise serializers.ValidationError("Filename is required.")
        return filename

    def validate(self, attrs):
        attrs = super().validate(attrs)
        kind = attrs["kind"]
        rules = get_kind_rules(kind)

        content_type = str(attrs["content_type"]).strip().lower()
        attrs["content_type"] = content_type

        allowed = rules["allowed_content_types"]
        if allowed and content_type not in allowed:
            raise serializers.ValidationError({"content_type": "Unsupported file type."})

        if attrs["size_bytes"] > rules["max_size"]:
            raise serializers.ValidationError(
                {"size_bytes": f"File exceeds the maximum allowed size of {rules['max_size']} bytes."}
            )

        detected, _ = mimetypes.guess_type(attrs["filename"])
        if detected and detected != content_type:
            raise serializers.ValidationError({"content_type": "File content type does not match filename extension."})

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        kind = validated_data["kind"]
        rules = get_kind_rules(kind)
        ttl = rules["ttl_seconds"]

        # Pre-compute keys using a pre-generated UUID so we avoid a two-step
        # create+update and the unique constraint on key="" for concurrent uploads.
        asset_id = uuid_module.uuid4()
        pending_key = build_pending_asset_key(kind, str(asset_id), validated_data["filename"])
        final_key = build_asset_key(kind, str(asset_id), validated_data["filename"])

        asset = Asset.objects.create(
            id=asset_id,
            owner=request.user,
            kind=kind,
            visibility=rules["visibility"],
            status=Asset.Status.INITIATED,
            pending_key=pending_key,
            key=final_key,
            original_filename=validated_data["filename"],
            content_type_client=validated_data["content_type"],
            size_client=validated_data["size_bytes"],
            is_temporary=True,
            draft_token=validated_data.get("draft_token", ""),
            expires_at=timezone.now() + timedelta(seconds=ttl + 3600),
        )

        storage = default_storage
        cleanup_expired_pending_files(
            storage,
            prefix=f"assets-pending/{kind}/",
            max_age_seconds=rules["pending_max_age_seconds"],
        )

        signed_upload_url = generate_presigned_upload_url(
            storage,
            key=pending_key,
            content_type=validated_data["content_type"],
            ttl_seconds=ttl,
        )

        if request:
            complete_url = request.build_absolute_uri(reverse("asset-complete-upload", kwargs={"asset_id": asset.id}))
        else:
            complete_url = reverse("asset-complete-upload", kwargs={"asset_id": asset.id})

        return {
            "asset_id": asset.id,
            "upload_url": build_public_media_url(pending_key, request=request, signed_url=signed_upload_url),
            "upload_method": "PUT",
            "upload_headers": {"Content-Type": validated_data["content_type"]},
            "expires_in": ttl,
            "complete_url": complete_url,
        }


class AssetUploadTargetSerializer(serializers.Serializer):
    """Read-only serializer for the initiate-upload response."""

    asset_id = serializers.UUIDField(read_only=True)
    upload_url = serializers.URLField(read_only=True)
    upload_method = serializers.CharField(read_only=True)
    upload_headers = serializers.DictField(child=serializers.CharField(), read_only=True)
    expires_in = serializers.IntegerField(read_only=True)
    complete_url = serializers.URLField(read_only=True)

    def to_representation(self, instance):
        return instance  # instance is already a dict


class AssetSerializer(serializers.ModelSerializer):
    """Minimal read-only representation of a confirmed Asset."""

    class Meta:
        model = Asset
        fields = (
            "id",
            "kind",
            "visibility",
            "status",
            "original_filename",
            "content_type_client",
            "size_client",
            "is_temporary",
            "draft_token",
            "created_at",
            "uploaded_at",
            "confirmed_at",
        )
        read_only_fields = fields


class AssetCompleteUploadSerializer(serializers.Serializer):
    """
    Confirm a pending upload.

    Validates the object in S3, moves it from its pending key to the final key,
    and marks the Asset as CONFIRMED.
    """

    def validate(self, attrs):
        request = self.context.get("request")
        asset = self.context.get("asset")

        if asset is None:
            raise serializers.ValidationError("Asset not found.")

        if request and not request.user.is_staff and asset.owner != request.user:
            raise serializers.ValidationError("Asset not found.")

        if asset.status not in (Asset.Status.INITIATED, Asset.Status.UPLOADED):
            raise serializers.ValidationError("Asset cannot be confirmed in its current state.")

        if not asset.pending_key:
            raise serializers.ValidationError("Asset has no pending upload to confirm.")

        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            # Re-read under a row lock: two concurrent confirmations must not both
            # move the object.
            asset = Asset.objects.select_for_update().get(pk=self.context["asset"].pk)
            if asset.status not in (Asset.Status.INITIATED, Asset.Status.UPLOADED) or not asset.pending_key:
                raise serializers.ValidationError("Asset cannot be confirmed in its current state.")

            move_pending_to_confirmed(
                default_storage,
                pending_key=asset.pending_key,
                final_key=asset.key,
                content_type=asset.content_type_client,
                expected_size=asset.size_client,
            )

            asset.pending_key = ""
            asset.status = Asset.Status.CONFIRMED
            asset.confirmed_at = timezone.now()
            asset.save(update_fields=["pending_key", "status", "confirmed_at"])

        return asset
