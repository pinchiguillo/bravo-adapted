from rest_framework import serializers

from apps.organization.serializers import AnnouncementSerializer

from .models import Job


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
