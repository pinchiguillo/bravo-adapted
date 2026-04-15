from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.management.models import FeatureFlag
from apps.organization.models import (
    AllowedCity,
    Announcement,
    AnnouncementStatusChange,
    Category,
    Organization,
    PlanTierCatalog,
    ServiceCatalog,
)
from apps.organization.serializers import (
    AnnouncementSerializer,
    AnnouncementStatusChangeSerializer,
    OrganizationRatingMixin,
    PlanTierCatalogSerializer,
)
from apps.organization.serializers.catalog import CatalogReferenceField

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
    plan_tier = serializers.SerializerMethodField()

    @extend_schema_field(PlanTierCatalogSerializer(allow_null=True))
    def get_plan_tier(self, obj):
        pricing = getattr(obj, "pricing", None)
        if pricing is None or pricing.plan_tier_id is None:
            return None
        return PlanTierCatalogSerializer(pricing.plan_tier).data

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
            "plan_tier",
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
                subservice = plan_price.subservice
                if subservice.announcement.organization_id != announcement.organization_id:
                    raise serializers.ValidationError(
                        {"plan_price": "Plan price does not belong to the selected announcement."}
                    )
                if subservice.announcement_id != announcement.id:
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


class ManagementAllowedCitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AllowedCity
        fields = (
            "uuid",
            "name",
        )
        read_only_fields = ("uuid",)


class ManagementPlanTierCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanTierCatalog
        fields = (
            "uuid",
            "key",
            "name",
            "description",
            "sort_order",
        )
        read_only_fields = ("uuid",)


class ManagementServiceCatalogSerializer(serializers.ModelSerializer):
    category = CatalogReferenceField(read_only=True, slug_field="uuid")
    category_uuid = serializers.SlugRelatedField(
        source="category",
        queryset=Category.objects.all(),
        slug_field="uuid",
        write_only=True,
    )

    class Meta:
        model = ServiceCatalog
        fields = (
            "uuid",
            "name",
            "description",
            "category",
            "category_uuid",
        )
        read_only_fields = ("uuid", "category")


class ManagementAnnouncementSerializer(AnnouncementSerializer):
    class Meta(AnnouncementSerializer.Meta):
        read_only_fields = (
            "uuid",
            "organization",
            "view_count",
            "created_at",
            "updated_at",
        )


class ManagementAnnouncementStatusChangeSerializer(AnnouncementStatusChangeSerializer):
    class Meta(AnnouncementStatusChangeSerializer.Meta):
        read_only_fields = list(AnnouncementStatusChangeSerializer.Meta.read_only_fields) + [
            'from_status',
            'to_status',
            'changed_by',
            'announcement',
        ]
