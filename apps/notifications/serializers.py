from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationTemplate,
)
from .services import emit_notification, summarize_notification


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = (
            "in_app_enabled",
            "email_enabled",
            "push_enabled",
            "system_notifications",
            "chat_notifications",
            "marketing_notifications",
        )


class NotificationRecipientSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="notification.title", read_only=True)
    body = serializers.CharField(source="notification.body", read_only=True)
    severity = serializers.CharField(source="notification.severity", read_only=True)
    category = serializers.CharField(source="notification.category", read_only=True)
    origin = serializers.CharField(source="notification.origin", read_only=True)
    action_url = serializers.CharField(source="notification.action_url", read_only=True)
    created_at = serializers.DateTimeField(source="notification.created_at", read_only=True)
    channels = serializers.SerializerMethodField()

    class Meta:
        model = NotificationRecipient
        fields = (
            "uuid",
            "title",
            "body",
            "severity",
            "category",
            "origin",
            "action_url",
            "created_at",
            "read_at",
            "channels",
        )
        read_only_fields = fields

    def get_channels(self, obj):
        channels = []
        if obj.in_app_enabled:
            channels.append(Notification.Channel.IN_APP)
        if obj.email_enabled:
            channels.append(Notification.Channel.EMAIL)
        if obj.push_enabled:
            channels.append(Notification.Channel.PUSH)
        return channels


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = (
            "uuid",
            "key",
            "name",
            "title_template",
            "body_template",
            "category",
            "severity",
            "default_channels",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")


class ManagementNotificationSerializer(serializers.ModelSerializer):
    recipient_count = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()
    email_status_counts = serializers.SerializerMethodField()
    push_status_counts = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "uuid",
            "origin",
            "category",
            "severity",
            "target_type",
            "target_label",
            "target_uuid",
            "title",
            "body",
            "action_url",
            "requested_channels",
            "payload",
            "created_at",
            "created_by_email",
            "recipient_count",
            "read_count",
            "email_status_counts",
            "push_status_counts",
        )
        read_only_fields = fields

    def _summary(self, obj):
        if not hasattr(obj, "_notification_summary"):
            obj._notification_summary = summarize_notification(obj)
        return obj._notification_summary

    def get_recipient_count(self, obj):
        return self._summary(obj)["recipient_count"]

    def get_read_count(self, obj):
        return self._summary(obj)["read_count"]

    def get_email_status_counts(self, obj):
        return self._summary(obj)["email_status_counts"]

    def get_push_status_counts(self, obj):
        return self._summary(obj)["push_status_counts"]

    def get_created_by_email(self, obj):
        created_by = getattr(obj, "created_by", None)
        return getattr(created_by, "email", None)


class ManagementSendNotificationSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)
    template_key = serializers.SlugField(required=False, allow_blank=True)
    target_type = serializers.ChoiceField(choices=Notification.TargetType.choices)
    target_uuid = serializers.UUIDField(required=False)
    category = serializers.ChoiceField(choices=Notification.Category.choices)
    severity = serializers.ChoiceField(
        choices=Notification.Severity.choices,
        default=Notification.Severity.MEDIUM,
    )
    action_url = serializers.CharField(required=False, allow_blank=True, max_length=255)
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=Notification.Channel.choices),
        allow_empty=False,
    )
    payload = serializers.JSONField(required=False)

    def validate(self, attrs):
        target_type = attrs["target_type"]
        target_uuid = attrs.get("target_uuid")

        if target_type in {
            Notification.TargetType.USER,
            Notification.TargetType.ORGANIZATION,
        } and target_uuid is None:
            raise serializers.ValidationError({"target_uuid": "This field is required for the selected target_type."})

        if target_type == Notification.TargetType.BROADCAST and target_uuid is not None:
            raise serializers.ValidationError({"target_uuid": "Do not send target_uuid for broadcast notifications."})

        if not attrs.get("template_key") and not attrs.get("title", "").strip():
            raise serializers.ValidationError({"title": "Title is required when no template is provided."})

        if not attrs.get("template_key") and not attrs.get("body", "").strip():
            raise serializers.ValidationError({"body": "Body is required when no template is provided."})

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return emit_notification(
            title=validated_data.get("title", ""),
            body=validated_data.get("body", ""),
            origin=Notification.Origin.COMMUNICATION,
            category=validated_data["category"],
            severity=validated_data["severity"],
            target_type=validated_data["target_type"],
            target_uuid=validated_data.get("target_uuid"),
            requested_channels=validated_data["channels"],
            payload=validated_data.get("payload", {}),
            action_url=validated_data.get("action_url", ""),
            created_by=request.user,
            template_key=validated_data.get("template_key", ""),
        )


class NotificationUnreadCountSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()


class NotificationRecipientReadSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)

