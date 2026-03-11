from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from jobs.models import Job
from organization.models import Organization


class ManagementUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = get_user_model()
        fields = (
            "id",
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
        read_only_fields = ("id", "uuid")

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


class ManagementOrganizationSerializer(serializers.ModelSerializer):
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
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")


class ManagementJobSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(queryset=get_user_model().objects.all(), slug_field="uuid")
    organization = serializers.SlugRelatedField(queryset=Organization.objects.all(), slug_field="uuid")

    class Meta:
        model = Job
        fields = (
            "id",
            "uuid",
            "user",
            "organization",
            "plan_price",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "uuid", "created_at", "updated_at")

    def validate(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        plan_price = attrs.get("plan_price", getattr(self.instance, "plan_price", None))
        if organization is not None and plan_price is not None:
            if plan_price.service.organization_id != organization.id:
                raise serializers.ValidationError(
                    {"plan_price": "Plan price does not belong to the selected organization."}
                )
        return attrs
