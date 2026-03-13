from rest_framework import serializers

from .models import Job


class JobSerializer(serializers.ModelSerializer):
    PUBLIC_ALLOWED_STATUSES = {
        Job.Status.PENDING,
        Job.Status.ACTIVE,
        Job.Status.COMPLETED,
        Job.Status.REJECTED,
    }

    class Meta:
        model = Job
        fields = (
            "id",
            "uuid",
            "user",
            "organization",
            "plan_price",
            "status",
            "organization_rating",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "uuid", "user", "created_at", "updated_at")

    def validate(self, attrs):
        if self.instance is None:
            requested_status = attrs.get("status", Job.Status.PENDING)
            if requested_status != Job.Status.PENDING:
                raise serializers.ValidationError(
                    {"status": "New jobs must start in pending status."}
                )
            attrs["status"] = Job.Status.PENDING
            return self._validate_plan_price_belongs_to_organization(attrs)

        errors = {}
        for field_name in ("organization", "plan_price", "status"):
            if field_name not in attrs:
                continue
            if attrs[field_name] != getattr(self.instance, field_name):
                errors[field_name] = f"{field_name.replace('_', ' ').capitalize()} cannot be changed."

        if errors:
            raise serializers.ValidationError(errors)

        self._validate_rating_can_be_set(attrs)
        return self._validate_plan_price_belongs_to_organization(attrs)

    def _validate_plan_price_belongs_to_organization(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        plan_price = attrs.get("plan_price", getattr(self.instance, "plan_price", None))
        if organization is not None and plan_price is not None:
            if plan_price.subservice.service.organization_id != organization.id:
                raise serializers.ValidationError(
                    {"plan_price": "Plan price does not belong to the selected organization."}
                )
        return attrs

    def validate_status(self, value):
        if value not in self.PUBLIC_ALLOWED_STATUSES:
            raise serializers.ValidationError("Status is not allowed in this endpoint.")
        return value

    def _validate_rating_can_be_set(self, attrs):
        if "organization_rating" not in attrs:
            return

        job_status = attrs.get("status", getattr(self.instance, "status", Job.Status.PENDING))
        if job_status != Job.Status.COMPLETED:
            raise serializers.ValidationError(
                {"organization_rating": "Organization rating can only be set for completed jobs."}
            )
