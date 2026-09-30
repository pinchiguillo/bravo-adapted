from rest_framework import serializers

from apps.job_chat.models import JobChatMessage
from apps.organization.models import Announcement, ServicePrice
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
    """Request a job on the announcement given in the URL (context["announcement"]).

    Status and rating are not writable here: every job starts as pending.
    """

    # Optional cross-check against the URL announcement.
    announcement = serializers.PrimaryKeyRelatedField(
        queryset=Announcement.objects.all(),
        required=False,
        allow_null=True,
    )
    plan_price = serializers.PrimaryKeyRelatedField(
        queryset=ServicePrice.objects.select_related("subservice"),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Job
        fields = ("announcement", "plan_price")

    def validate(self, attrs):
        announcement = self.context["announcement"]
        requester = self.context["request"].user

        if attrs.get("announcement") not in (None, announcement):
            raise serializers.ValidationError(
                {"announcement": "Announcement in request body does not match the URL announcement."}
            )
        if announcement.status != Announcement.Status.ACTIVE:
            raise serializers.ValidationError({"announcement": "This announcement is not accepting requests."})
        if announcement.organization.user_id == requester.id:
            raise serializers.ValidationError({"announcement": "You cannot request your own announcement."})

        plan_price = attrs.get("plan_price")
        if plan_price is not None and plan_price.subservice.announcement_id != announcement.id:
            raise serializers.ValidationError({"plan_price": "This price does not belong to the announcement."})
        return attrs


class JobUpdateSerializer(serializers.ModelSerializer):
    """Requesters move a job through Job.REQUESTER_TRANSITIONS and rate it once completed."""

    class Meta:
        model = Job
        fields = ("status", "organization_rating")

    def validate(self, attrs):
        job = self.instance
        actor = self.context["request"].user
        new_status = attrs.get("status", job.status)

        allowed = Job.REQUESTER_TRANSITIONS.get(job.status, set())
        if new_status != job.status and not actor.is_staff and new_status not in allowed:
            raise serializers.ValidationError({"status": f"A job cannot move from '{job.status}' to '{new_status}'."})
        if attrs.get("organization_rating") is not None and new_status != Job.Status.COMPLETED:
            raise serializers.ValidationError({"organization_rating": "Only completed jobs can be rated."})
        return attrs


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

    # The last_message_* attributes are annotated by JobViewSet.get_queryset, so
    # listing N jobs costs a constant number of queries.
    def get_last_message_time(self, obj) -> str | None:
        last_message_at = getattr(obj, "last_message_at", None)
        return last_message_at.isoformat() if last_message_at else None

    def get_last_message_preview(self, obj) -> str | None:
        if getattr(obj, "last_message_at", None) is None:
            return None
        if obj.last_message_type == JobChatMessage.MessageType.PLAIN_TEXT:
            return obj.last_message_content[:60]
        return "📋 Propuesta"

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
