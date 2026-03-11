import os

from django.conf import settings
from django.urls import reverse
from rest_framework import serializers

from .models import Job, JobChatAttachment, JobChatMessage


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

        return self._validate_plan_price_belongs_to_organization(attrs)

    def _validate_plan_price_belongs_to_organization(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        plan_price = attrs.get("plan_price", getattr(self.instance, "plan_price", None))
        if organization is not None and plan_price is not None:
            if plan_price.service.organization_id != organization.id:
                raise serializers.ValidationError(
                    {"plan_price": "Plan price does not belong to the selected organization."}
                )
        return attrs

    def validate_status(self, value):
        if value not in self.PUBLIC_ALLOWED_STATUSES:
            raise serializers.ValidationError("Status is not allowed in this endpoint.")
        return value

class JobChatAttachmentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()
    filename = serializers.SerializerMethodField()

    def validate_file(self, file):
        allowed_content_types = set(getattr(settings, "JOB_CHAT_ATTACHMENT_ALLOWED_CONTENT_TYPES", []))
        content_type = getattr(file, "content_type", "")
        detected_content_type = self._detect_content_type(file)

        if allowed_content_types and detected_content_type not in allowed_content_types:
            raise serializers.ValidationError("Unsupported file type.")
        if content_type and detected_content_type != content_type:
            raise serializers.ValidationError("File content type does not match file contents.")

        max_bytes = getattr(settings, "JOB_CHAT_ATTACHMENT_MAX_BYTES", 5 * 1024 * 1024)
        if file.size > max_bytes:
            raise serializers.ValidationError(
                f"File exceeds the maximum allowed size of {max_bytes} bytes."
            )
        return file

    def get_download_url(self, obj):
        request = self.context.get("request")
        url = reverse(
            "jobs-download-attachment",
            kwargs={
                "uuid": obj.message.chat.job.uuid,
                "message_id": obj.message_id,
                "attachment_id": obj.id,
            },
        )
        if request is None:
            return url
        return request.build_absolute_uri(url)

    def get_filename(self, obj):
        return os.path.basename(obj.file.name)

    def _detect_content_type(self, file):
        file.seek(0)
        sample = file.read(512)
        file.seek(0)

        if sample.startswith(b"%PDF-"):
            return "application/pdf"
        if sample.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if sample.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if self._is_utf8_text(sample):
            return "text/plain"
        return "application/octet-stream"

    def _is_utf8_text(self, sample):
        if b"\x00" in sample:
            return False
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True

    class Meta:
        model = JobChatAttachment
        fields = ("id", "message", "file", "filename", "download_url", "uploaded_by", "created_at")
        read_only_fields = ("id", "message", "filename", "download_url", "uploaded_by", "created_at")


class JobChatMessageSerializer(serializers.ModelSerializer):
    attachments = JobChatAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = JobChatMessage
        fields = ("id", "uuid", "chat", "sender", "content", "created_at", "attachments")
        read_only_fields = ("id", "uuid", "chat", "sender", "created_at", "attachments")

    def validate(self, attrs):
        content = attrs.get("content", "")
        if not content.strip():
            raise serializers.ValidationError({"content": "Message content cannot be empty."})
        return attrs
