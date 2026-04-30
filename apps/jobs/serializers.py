from rest_framework import serializers

from apps.organization.serializers import AnnouncementSerializer

from .models import Job


class JobListUserSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)


class JobListProviderSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class JobListPriceSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    currency = serializers.CharField(read_only=True)
    charging_type = serializers.CharField(read_only=True)
    effective_from = serializers.DateField(read_only=True)
    effective_to = serializers.DateField(read_only=True, allow_null=True)


class JobSerializer(serializers.ModelSerializer):
    announcement_details = AnnouncementSerializer(source="announcement", read_only=True)

    class Meta:
        model = Job
        fields = (
            "id",
            "uuid",
            "user",
            "announcement",
            "announcement_details",
            "plan_price",
            "status",
            "organization_rating",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "uuid", "created_at", "updated_at")


class JobCreateSerializer(serializers.ModelSerializer):
    # announcement is resolved from the URL in the view; the body field is optional
    # and only used as a cross-check when provided.
    announcement = serializers.PrimaryKeyRelatedField(
        queryset=Job._meta.get_field("announcement").related_model.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Job
        fields = (
            "announcement",
            "plan_price",
            "status",
            "organization_rating",
        )


class JobUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = (
            "status",
            "organization_rating",
            "plan_price",
        )


class JobListSerializer(serializers.ModelSerializer):
    announcement = serializers.UUIDField(source="announcement.uuid", read_only=True)
    user = JobListUserSerializer(read_only=True)
    provider = JobListProviderSerializer(source="announcement.organization", read_only=True)
    price = JobListPriceSerializer(source="plan_price", read_only=True)
    organization_name = serializers.CharField(source="announcement.organization.name", read_only=True)
    announcement_name = serializers.CharField(source="announcement.name", read_only=True)
    announcement_category = serializers.CharField(source="announcement.category", read_only=True)
    last_message_time = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    def get_last_message_time(self, obj):
        if hasattr(obj, "chat") and obj.chat:
            msg = obj.chat.messages.order_by("-created_at").first()
            return msg.created_at.isoformat() if msg else None
        return None

    def get_last_message_preview(self, obj):
        if hasattr(obj, "chat") and obj.chat:
            msg = obj.chat.messages.order_by("-created_at").first()
            if msg:
                return msg.content[:60] if msg.type == "plain_text" else "📋 Propuesta"
        return None

    def get_unread_count(self, obj):
        return 0

    class Meta:
        model = Job
        fields = (
            "uuid",
            "status",
            "announcement",
            "price",
            "user",
            "provider",
            "organization_name",
            "announcement_name",
            "announcement_category",
            "last_message_time",
            "last_message_preview",
            "unread_count",
            "created_at",
        )
        read_only_fields = fields
