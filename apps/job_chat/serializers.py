import json
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.assets.models import Asset
from common.money import Currency

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
        fields = ("uuid", "user_id", "username", "type", "content", "attachments", "created_at", "updated_at")
        read_only_fields = ("uuid", "user_id", "username", "type", "created_at", "updated_at", "attachments")


PROPOSAL_WIDGET = "proposal"
PROPOSAL_PENDING = "pending"
PROPOSAL_ANSWERS = ("accepted", "rejected")
PROPOSAL_PRICE_MODES = ("total", "hourly", "daily", "monthly", "per_sqm", "per_unit")


class ProposalDataSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    category = serializers.CharField(required=False, allow_blank=True, max_length=100)
    subcategory = serializers.CharField(required=False, allow_blank=True, max_length=100)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    price_mode = serializers.ChoiceField(choices=PROPOSAL_PRICE_MODES)
    currency = serializers.ChoiceField(choices=Currency.values)


def normalize_proposal_widget(raw_content):
    """Validate a proposal widget and return its canonical JSON content.

    Unknown keys are dropped and the status is owned by the server: a new
    proposal always starts as pending, whatever the client sent.
    """
    try:
        widget = json.loads(raw_content)
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError({"content": "Widget content must be valid JSON."}) from exc
    if not isinstance(widget, dict) or widget.get("widget_type") != PROPOSAL_WIDGET:
        raise serializers.ValidationError({"content": "Unsupported widget type."})

    proposal = ProposalDataSerializer(data=widget.get("data"))
    if not proposal.is_valid():
        raise serializers.ValidationError({"content": proposal.errors})

    data = dict(proposal.validated_data)
    # JSON has no decimal type and the clients read price as a number; it has
    # already been validated as a non-negative amount with two decimals.
    data["price"] = float(data["price"])
    data["status"] = PROPOSAL_PENDING
    return json.dumps({"widget_type": PROPOSAL_WIDGET, "data": data})


class JobChatMessageCreateSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(
        choices=JobChatMessage.MessageType.choices,
        default=JobChatMessage.MessageType.PLAIN_TEXT,
        required=False,
    )
    content = serializers.CharField(max_length=5000)

    class Meta:
        model = JobChatMessage
        fields = ("type", "content")

    def validate(self, attrs):
        if attrs.get("type") == JobChatMessage.MessageType.WIDGET:
            attrs["content"] = normalize_proposal_widget(attrs["content"])
        return attrs


class JobChatSerializer(serializers.ModelSerializer):
    messages = JobChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = JobChat
        fields = ("uuid", "job", "messages", "created_at", "updated_at")
        read_only_fields = ("uuid", "job", "messages", "created_at", "updated_at")


class ProposalStatusUpdateSerializer(serializers.Serializer):
    """Update the status of a proposal widget message."""

    status = serializers.ChoiceField(choices=PROPOSAL_ANSWERS)


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

        with transaction.atomic():
            # Lock the asset so two concurrent requests cannot attach it twice.
            asset = Asset.objects.select_for_update().get(pk=self.context["asset"].pk)
            if asset.status != Asset.Status.CONFIRMED:
                raise serializers.ValidationError({"asset_id": "Asset is no longer available for attachment."})

            attachment = JobChatAttachment.objects.create(message=message, asset=asset)
            asset.status = Asset.Status.ATTACHED
            asset.is_temporary = False
            asset.save(update_fields=["status", "is_temporary"])

        return attachment
