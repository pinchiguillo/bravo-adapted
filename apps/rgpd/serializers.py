from rest_framework import serializers

from .models import RgpdAnonymousConsent, RgpdConsent, RgpdLegalDocument


class RgpdConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RgpdConsent
        fields = (
            "cookies_accepted",
            "cookies_accepted_at",
            "cookies_version",
            "privacy_policy_accepted",
            "privacy_policy_accepted_at",
            "privacy_policy_version",
            "terms_and_conditions_accepted",
            "terms_and_conditions_accepted_at",
            "terms_and_conditions_version",
            "source",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "cookies_accepted_at",
            "privacy_policy_accepted_at",
            "terms_and_conditions_accepted_at",
            "created_at",
            "updated_at",
        )


class RgpdConsentUpsertSerializer(serializers.ModelSerializer):
    class Meta:
        model = RgpdConsent
        fields = (
            "cookies_accepted",
            "cookies_version",
            "privacy_policy_accepted",
            "privacy_policy_version",
            "terms_and_conditions_accepted",
            "terms_and_conditions_version",
            "source",
        )
        extra_kwargs = {
            "cookies_accepted": {"required": False},
            "cookies_version": {"required": False, "allow_blank": True},
            "privacy_policy_accepted": {"required": False},
            "privacy_policy_version": {"required": False, "allow_blank": True},
            "terms_and_conditions_accepted": {"required": False},
            "terms_and_conditions_version": {"required": False, "allow_blank": True},
            "source": {"required": False, "allow_blank": True},
        }


class RgpdAnonymousConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RgpdAnonymousConsent
        fields = (
            "identifier",
            "cookies_accepted",
            "cookies_accepted_at",
            "cookies_version",
            "privacy_policy_accepted",
            "privacy_policy_accepted_at",
            "privacy_policy_version",
            "terms_and_conditions_accepted",
            "terms_and_conditions_accepted_at",
            "terms_and_conditions_version",
            "source",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "cookies_accepted_at",
            "privacy_policy_accepted_at",
            "terms_and_conditions_accepted_at",
            "created_at",
            "updated_at",
        )


class RgpdAnonymousConsentUpsertSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=128, required=False)
    write_token = serializers.CharField(max_length=128, required=False)
    cookies_accepted = serializers.BooleanField(required=False)
    cookies_version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    privacy_policy_accepted = serializers.BooleanField(required=False)
    privacy_policy_version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    terms_and_conditions_accepted = serializers.BooleanField(required=False)
    terms_and_conditions_version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    source = serializers.CharField(required=False, allow_blank=True, max_length=64)

    def validate(self, attrs):
        identifier = attrs.get("identifier")
        write_token = attrs.get("write_token")
        if bool(identifier) != bool(write_token):
            raise serializers.ValidationError(
                "identifier and write_token must be provided together."
            )
        return attrs


class RgpdLegalDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RgpdLegalDocument
        fields = (
            "uuid",
            "document_type",
            "file",
            "original_name",
            "content_type",
            "size_bytes",
            "created_at",
        )
        read_only_fields = (
            "uuid",
            "original_name",
            "content_type",
            "size_bytes",
            "created_at",
        )
        extra_kwargs = {
            "document_type": {"trim_whitespace": True},
        }

    def validate_document_type(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("This field may not be blank.")
        return normalized

    def validate_file(self, value):
        allowed_types = set(self.context["allowed_content_types"])
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Unsupported legal document content type.")
        if value.size > self.context["max_bytes"]:
            raise serializers.ValidationError("Legal document exceeds maximum allowed size.")
        return value

    def create(self, validated_data):
        uploaded_file = validated_data["file"]
        return RgpdLegalDocument.objects.create(
            user=self.context["request"].user,
            document_type=validated_data["document_type"],
            file=uploaded_file,
            original_name=uploaded_file.name,
            content_type=uploaded_file.content_type or "",
            size_bytes=uploaded_file.size,
        )
