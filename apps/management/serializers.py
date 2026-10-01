from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.assets.models import Asset
from apps.auth.sessions import revoke_all_refresh_tokens
from apps.job_chat.models import JobChat
from apps.job_chat.serializers import JobChatMessageSerializer
from apps.jobs.models import Job
from apps.management.models import FeatureFlag
from apps.management.permissions import SELF_LOCKOUT_FIELDS, ensure_can_change_roles
from apps.organization.models import (
    AllowedCity,
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


class ManagementUserOrganizationSerializer(serializers.ModelSerializer):
    admin_url = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = (
            "uuid",
            "name",
            "admin_url",
        )
        read_only_fields = fields

    def get_admin_url(self, obj):
        request = self.context.get("request")
        admin_path = f"/admin/organization/organization/{obj.pk}/change/"

        if request is None:
            return admin_path

        return request.build_absolute_uri(admin_path)


class ManagementUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8 if settings.AUTH_ENFORCE_PASSWORD_RESTRICTIONS else None,
    )
    has_organization = serializers.SerializerMethodField()
    is_provider = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()

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
            "is_superuser",
            "is_active",
            "has_organization",
            "is_provider",
            "organization",
        )
        read_only_fields = ("uuid",)

    @extend_schema_field(serializers.BooleanField())
    def get_has_organization(self, obj):
        return getattr(obj, "organization", None) is not None

    @extend_schema_field(serializers.BooleanField())
    def get_is_provider(self, obj):
        return self.get_has_organization(obj)

    @extend_schema_field(ManagementUserOrganizationSerializer(allow_null=True))
    def get_organization(self, obj):
        organization = getattr(obj, "organization", None)
        if organization is None:
            return None

        return ManagementUserOrganizationSerializer(
            organization,
            context=self.context,
        ).data

    def validate(self, attrs):
        errors = {}

        if self.instance is None and not attrs.get("password"):
            errors["password"] = "This field is required."  # noqa: S105 - error message, not a password

        if self.instance is None and (
            "is_staff" in self.initial_data or "is_superuser" in self.initial_data
        ):
            errors["is_staff"] = "is_staff cannot be changed in this endpoint."
            if "is_superuser" in self.initial_data:
                errors["is_superuser"] = "is_superuser cannot be changed in this endpoint."

        if errors:
            raise serializers.ValidationError(errors)

        if self.instance is not None:
            # Compare values, not submitted keys: a form-encoded PUT turns missing
            # booleans into False, and echoing an unchanged value is harmless.
            changed = {
                field
                for field in SELF_LOCKOUT_FIELDS
                if field in attrs and attrs[field] != getattr(self.instance, field)
            }
            ensure_can_change_roles(self.context["request"].user, self.instance, changed)

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
        if validated_data.get("is_superuser") is True:
            validated_data["is_staff"] = True
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if password:
            # A reset password must end the sessions opened with the old one.
            revoke_all_refresh_tokens(instance.pk)
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
        read_only_fields = [
            *AnnouncementStatusChangeSerializer.Meta.read_only_fields,
            'from_status',
            'to_status',
            'changed_by',
            'announcement',
        ]


class ManagementAssetSerializer(serializers.ModelSerializer):
    owner_email = serializers.CharField(source='owner.email', read_only=True)

    class Meta:
        model = Asset
        fields = (
            'id',
            'kind',
            'visibility',
            'status',
            'original_filename',
            'content_type_client',
            'size_client',
            'size_actual',
            'is_temporary',
            'owner_email',
            'created_at',
            'confirmed_at',
        )
        read_only_fields = fields


class ManagementUserSummarySerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    full_name = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField())
    def get_full_name(self, obj):
        return " ".join(
            part.strip()
            for part in [getattr(obj, "first_name", ""), getattr(obj, "last_name", "")]
            if part and part.strip()
        )


class ManagementOrganizationSummarySerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)


class ManagementAnnouncementSummarySerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    location = serializers.CharField(read_only=True)


class ManagementServicePriceSummarySerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    currency = serializers.CharField(read_only=True)
    charging_type = serializers.CharField(read_only=True)


class ManagementJobChatSummarySerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    message_count = serializers.IntegerField(read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True, allow_null=True)
    last_message_preview = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)


class ManagementJobSerializer(serializers.ModelSerializer):
    user = ManagementUserSummarySerializer(read_only=True)
    provider = serializers.SerializerMethodField()
    announcement = serializers.SerializerMethodField()
    plan_price = ManagementServicePriceSummarySerializer(read_only=True)
    chat = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = (
            "id",
            "uuid",
            "status",
            "organization_rating",
            "created_at",
            "updated_at",
            "user",
            "provider",
            "announcement",
            "plan_price",
            "chat",
        )
        read_only_fields = fields

    @extend_schema_field(ManagementOrganizationSummarySerializer())
    def get_provider(self, obj):
        return ManagementOrganizationSummarySerializer(obj.announcement.organization).data

    @extend_schema_field(ManagementAnnouncementSummarySerializer())
    def get_announcement(self, obj):
        return ManagementAnnouncementSummarySerializer(obj.announcement).data

    @extend_schema_field(ManagementJobChatSummarySerializer(allow_null=True))
    def get_chat(self, obj):
        chat = getattr(obj, "chat", None)
        if chat is None:
            return None

        message_count = getattr(chat, "message_count", None)
        if message_count is None:
            message_count = chat.messages.count()

        last_message = getattr(chat, "_prefetched_last_message", None)
        if last_message is None:
            last_message = chat.messages.order_by("-created_at").first()

        last_message_preview = None
        last_message_time = None
        if last_message is not None:
            last_message_time = last_message.created_at
            last_message_preview = last_message.content[:120]

        return {
            "uuid": chat.uuid,
            "message_count": message_count,
            "last_message_time": last_message_time,
            "last_message_preview": last_message_preview,
        }


class ManagementJobChatListSerializer(serializers.ModelSerializer):
    job_uuid = serializers.UUIDField(source="job.uuid", read_only=True)
    job_status = serializers.CharField(source="job.status", read_only=True)
    user = ManagementUserSummarySerializer(source="job.user", read_only=True)
    provider = ManagementOrganizationSummarySerializer(
        source="job.announcement.organization",
        read_only=True,
    )
    announcement = ManagementAnnouncementSummarySerializer(source="job.announcement", read_only=True)
    message_count = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()

    class Meta:
        model = JobChat
        fields = (
            "uuid",
            "job_uuid",
            "job_status",
            "user",
            "provider",
            "announcement",
            "message_count",
            "last_message_time",
            "last_message_preview",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_message_count(self, obj):
        return getattr(obj, "message_count", obj.messages.count())

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_message_time(self, obj):
        last_message = getattr(obj, "_prefetched_last_message", None)
        if last_message is None:
            last_message = obj.messages.order_by("-created_at").first()
        return None if last_message is None else last_message.created_at

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_last_message_preview(self, obj):
        last_message = getattr(obj, "_prefetched_last_message", None)
        if last_message is None:
            last_message = obj.messages.order_by("-created_at").first()
        return None if last_message is None else last_message.content[:120]


class ManagementJobChatDetailSerializer(serializers.ModelSerializer):
    job_uuid = serializers.UUIDField(source="job.uuid", read_only=True)
    job_status = serializers.CharField(source="job.status", read_only=True)
    user = ManagementUserSummarySerializer(source="job.user", read_only=True)
    provider = ManagementOrganizationSummarySerializer(
        source="job.announcement.organization",
        read_only=True,
    )
    announcement = ManagementAnnouncementSummarySerializer(source="job.announcement", read_only=True)
    messages = JobChatMessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = JobChat
        fields = (
            "uuid",
            "job_uuid",
            "job_status",
            "user",
            "provider",
            "announcement",
            "message_count",
            "created_at",
            "updated_at",
            "messages",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_message_count(self, obj):
        return getattr(obj, "message_count", obj.messages.count())
