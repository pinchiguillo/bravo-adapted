from rest_framework import serializers

from apps.assets.models import Asset

from .models import JobChat, JobChatAttachment, JobChatMessage


class JobChatAttachmentSerializer(serializers.ModelSerializer):
    asset_id       = serializers.UUIDField(source="asset.id", read_only=True)
    filename       = serializers.CharField(source="asset.original_filename", read_only=True)
    content_type   = serializers.CharField(source="asset.content_type_client", read_only=True)
    size           = serializers.IntegerField(source="asset.size_client", read_only=True)

    class Meta:
        model = JobChatAttachment
        fields = ("uuid", "asset_id", "filename", "content_type", "size", "created_at")
        read_only_fields = fields


class JobChatMessageSerializer(serializers.ModelSerializer):
    attachments = JobChatAttachmentSerializer(many=True, read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = JobChatMessage
        fields = ("uuid", "user_id", "username", "content", "attachments", "created_at", "updated_at")
        read_only_fields = ("uuid", "user_id", "username", "created_at", "updated_at", "attachments")


class JobChatMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobChatMessage
        fields = ("content",)


class JobChatSerializer(serializers.ModelSerializer):
    messages = JobChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = JobChat
        fields = ("uuid", "job", "messages", "created_at", "updated_at")
        read_only_fields = ("uuid", "job", "messages", "created_at", "updated_at")


class JobChatAttachmentCreateSerializer(serializers.Serializer):
    """
    Attach a CONFIRMED Asset to a JobChatMessage.

    The asset must:
      - belong to request.user
      - have status CONFIRMED
      - have kind = job_chat_attachment
    """

    asset_id = serializers.UUIDField()

    def validate_asset_id(self, value):
        request = self.context["request"]
        try:
            asset = Asset.objects.get(id=value)
        except Asset.DoesNotExist as exc:
            raise serializers.ValidationError("Asset not found.") from exc

        if not request.user.is_staff and asset.owner != request.user:
            raise serializers.ValidationError("Asset not found.")

        if asset.status != Asset.Status.CONFIRMED:
            raise serializers.ValidationError("Asset is not confirmed yet. Complete the upload first.")

        if asset.kind != Asset.Kind.JOB_CHAT_ATTACHMENT:
            raise serializers.ValidationError("Asset kind is not valid for job chat attachments.")

        self.context["asset"] = asset
        return value

    def create(self, validated_data):
        message = self.context["message"]
        asset   = self.context["asset"]

        attachment = JobChatAttachment.objects.create(message=message, asset=asset)

        asset.status       = Asset.Status.ATTACHED
        asset.is_temporary = False
        asset.save(update_fields=["status", "is_temporary"])

        return attachment
