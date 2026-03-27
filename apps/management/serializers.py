from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.management.models import FeatureFlag
from apps.organization.models import Announcement, Category, Organization
from apps.organization.serializers import OrganizationRatingMixin

if apps.is_installed("apps.jobs"):
    from apps.jobs.models import Job


class ManagementUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8 if settings.AUTH_ENFORCE_PASSWORD_RESTRICTIONS else None,
    )

    class Meta:
        model = get_user_model()
        fields = (
            "uuid",
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "email_verified",
            "status",
            "is_staff",
            "is_active",
        )
        read_only_fields = ("uuid",)

    def validate(self, attrs):
        errors = {}

        if self.instance is None and not attrs.get("password"):
            errors["password"] = "This field is required."

        if "is_staff" in self.initial_data:
            errors["is_staff"] = "is_staff cannot be changed in this endpoint."

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def validate_password(self, value):
        if settings.AUTH_ENFORCE_PASSWORD_RESTRICTIONS:
            validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return get_user_model().objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class ManagementOrganizationSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
    user = serializers.SlugRelatedField(queryset=get_user_model().objects.all(), slug_field="uuid")

    class Meta:
        model = Organization
        fields = (
            "uuid",
            "user",
            "name",
            "legal_name",
            "tax_id",
            "billing_email",
            "billing_address",
            "billing_city",
            "billing_country",
            "billing_postal_code",
            "verification_level",
            "rating",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "rating", "created_at", "updated_at")

    def validate_user(self, value):
        if self.instance is None and Organization.objects.filter(user=value).exists():
            raise serializers.ValidationError("Selected user already has an organization.")
        return value


if apps.is_installed("apps.jobs"):
    class ManagementJobSerializer(serializers.ModelSerializer):
        user = serializers.SlugRelatedField(queryset=get_user_model().objects.all(), slug_field="uuid")
        announcement = serializers.SlugRelatedField(
            queryset=Announcement.objects.select_related("organization"),
            slug_field="uuid",
        )

        class Meta:
            model = Job
            fields = (
                "id",
                "uuid",
                "user",
                "announcement",
                "plan_price",
                "status",
                "organization_rating",
                "created_at",
                "updated_at",
            )
            read_only_fields = ("id", "uuid", "created_at", "updated_at")

        def validate(self, attrs):
            announcement = attrs.get("announcement", getattr(self.instance, "announcement", None))
            plan_price = attrs.get("plan_price", getattr(self.instance, "plan_price", None))
            if announcement is not None and plan_price is not None:
                service = plan_price.subservice.service
                if service.job.organization_id != announcement.organization_id:
                    raise serializers.ValidationError(
                        {"plan_price": "Plan price does not belong to the selected announcement."}
                    )
                if not announcement.services.filter(pk=service.pk).exists():
                    raise serializers.ValidationError(
                        {"plan_price": "Plan price does not belong to the selected announcement."}
                    )

            if "organization_rating" in attrs:
                job_status = attrs.get("status", getattr(self.instance, "status", None))
                if job_status != Job.Status.COMPLETED:
                    raise serializers.ValidationError(
                        {"organization_rating": "Organization rating can only be set for completed jobs."}
                    )
            return attrs


class ManagementFeatureFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureFlag
        fields = (
            "uuid",
            "key",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")


class ManagementCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "uuid",
            "name",
            "description",
        )
        read_only_fields = ("uuid",)
