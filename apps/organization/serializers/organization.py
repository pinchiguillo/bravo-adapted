from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import (
    Organization,
    OrganizationAvailabilityException,
    OrganizationAvailabilitySettings,
    OrganizationWeeklyAvailability,
)
from .catalog import PlanTierCatalogSerializer


class OrganizationRatingMixin(serializers.Serializer):
    rating = serializers.SerializerMethodField()

    def get_rating(self, obj) -> str | None:
        rating = getattr(obj, "calculated_rating", None)
        if rating is None:
            rating = obj.get_rating()
        if rating is None:
            return None
        return f"{rating:.2f}"


class OrganizationWeeklyAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationWeeklyAvailability
        fields = ("weekday", "start_time", "end_time")


class OrganizationAvailabilityExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationAvailabilityException
        fields = ("date", "mode", "start_time", "end_time", "label")


class OrganizationAvailabilitySettingsSerializer(serializers.ModelSerializer):
    weekly_schedule = OrganizationWeeklyAvailabilitySerializer(many=True, required=False)
    exceptions = OrganizationAvailabilityExceptionSerializer(many=True, required=False)

    class Meta:
        model = OrganizationAvailabilitySettings
        fields = ("enabled", "timezone", "weekly_schedule", "exceptions")

    enabled = serializers.BooleanField(source="is_enabled", required=False)

    def to_representation(self, instance):
        if instance is None:
            return {
                "enabled": False,
                "timezone": OrganizationAvailabilitySettings.DEFAULT_TIMEZONE,
                "weekly_schedule": [],
                "exceptions": [],
            }

        return {
            "enabled": instance.is_enabled,
            "timezone": instance.timezone,
            "weekly_schedule": OrganizationWeeklyAvailabilitySerializer(
                instance.weekly_schedule.all(),
                many=True,
            ).data,
            "exceptions": OrganizationAvailabilityExceptionSerializer(
                instance.exceptions.all(),
                many=True,
            ).data,
        }

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError("Use a valid IANA timezone.") from exc
        return value

    def validate_weekly_schedule(self, value):
        self._validate_time_ranges(
            value,
            date_key="weekday",
            error_message="Weekly availability ranges cannot overlap for the same weekday.",
        )
        return value

    def validate_exceptions(self, value):
        self._validate_time_ranges(
            value,
            date_key="date",
            error_message="Availability exceptions cannot overlap on the same date.",
        )
        return value

    def _validate_time_ranges(self, items, date_key, error_message):
        grouped_ranges = {}
        for item in items:
            start_time = item["start_time"]
            end_time = item["end_time"]
            if start_time >= end_time:
                raise serializers.ValidationError("end_time must be later than start_time.")
            group_key = item[date_key]
            grouped_ranges.setdefault(group_key, []).append((start_time, end_time))

        for ranges in grouped_ranges.values():
            ranges.sort(key=lambda current: current[0])
            for previous, current in zip(ranges, ranges[1:]):
                if current[0] < previous[1]:
                    raise serializers.ValidationError(error_message)


class OrganizationPublicSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
    is_approved = serializers.BooleanField(source="is_validated", read_only=True)
    plan_tier = serializers.SerializerMethodField()
    availability = OrganizationAvailabilitySettingsSerializer(
        source="availability_settings",
        read_only=True,
    )

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
            "name",
            "verification_level",
            "is_approved",
            "plan_tier",
            "rating",
            "availability",
        )
        read_only_fields = ("uuid",)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        availability = data.get("availability") or {}
        if not availability.get("enabled", False):
            data["availability"] = {
                "enabled": False,
                "timezone": availability.get(
                    "timezone",
                    OrganizationAvailabilitySettings.DEFAULT_TIMEZONE,
                ),
                "weekly_schedule": [],
                "exceptions": [],
            }
        return data


class OrganizationSerializer(OrganizationRatingMixin, serializers.ModelSerializer):
    is_approved = serializers.BooleanField(source="is_validated", read_only=True)
    plan_tier = serializers.SerializerMethodField()
    availability = OrganizationAvailabilitySettingsSerializer(
        source="availability_settings",
        required=False,
    )

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
            "name",
            "legal_name",
            "tax_id",
            "billing_email",
            "billing_address",
            "billing_city",
            "billing_country",
            "billing_postal_code",
            "verification_level",
            "is_approved",
            "plan_tier",
            "rating",
            "availability",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "verification_level",
            "is_approved",
            "rating",
            "created_at",
            "updated_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["availability"] = data.get("availability") or {
            "enabled": False,
            "timezone": OrganizationAvailabilitySettings.DEFAULT_TIMEZONE,
            "weekly_schedule": [],
            "exceptions": [],
        }
        return data

    @transaction.atomic
    def create(self, validated_data):
        availability_data = validated_data.pop("availability_settings", None)
        organization = super().create(validated_data)
        if availability_data is not None:
            self._apply_availability(organization, availability_data)
        return organization

    @transaction.atomic
    def update(self, instance, validated_data):
        availability_data = validated_data.pop("availability_settings", None)
        organization = super().update(instance, validated_data)
        if availability_data is not None:
            self._apply_availability(organization, availability_data)
        return organization

    def _apply_availability(self, organization, availability_data):
        settings_instance, _ = OrganizationAvailabilitySettings.objects.get_or_create(
            organization=organization,
            defaults={"timezone": OrganizationAvailabilitySettings.DEFAULT_TIMEZONE},
        )

        weekly_schedule = availability_data.pop("weekly_schedule", serializers.empty)
        exceptions = availability_data.pop("exceptions", serializers.empty)

        for field_name, value in availability_data.items():
            setattr(settings_instance, field_name, value)

        settings_instance.full_clean()
        settings_instance.save()

        if weekly_schedule is not serializers.empty:
            settings_instance.weekly_schedule.all().delete()
            OrganizationWeeklyAvailability.objects.bulk_create(
                [
                    OrganizationWeeklyAvailability(settings=settings_instance, **item)
                    for item in weekly_schedule
                ]
            )

        if exceptions is not serializers.empty:
            settings_instance.exceptions.all().delete()
            OrganizationAvailabilityException.objects.bulk_create(
                [
                    OrganizationAvailabilityException(settings=settings_instance, **item)
                    for item in exceptions
                ]
            )
