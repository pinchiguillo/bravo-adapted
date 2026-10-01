from rest_framework import serializers

from .models import (
    RgpdAnonymousConsent,
    RgpdConsent,
    RgpdDataRequest,
    RgpdLegalDocument,
    RgpdPolicyDocument,
    RgpdPolicyVersion,
)
from .services import (
    REQUIRED_POLICY_TYPES,
    build_policy_acceptance_snapshot,
    get_missing_required_policy_types,
)


class RgpdPolicyAcceptanceStatusSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()
    accepted_at = serializers.DateTimeField(allow_null=True)
    version = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)


class RgpdRequiredPolicySerializer(serializers.Serializer):
    type = serializers.CharField()
    version = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)


class RgpdConsentSerializer(serializers.ModelSerializer):
    accepted_documents = serializers.SerializerMethodField()
    required_documents = serializers.SerializerMethodField()
    requires_reacceptance = serializers.SerializerMethodField()

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
            "accepted_documents",
            "required_documents",
            "requires_reacceptance",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "cookies_accepted_at",
            "privacy_policy_accepted_at",
            "terms_and_conditions_accepted_at",
            "accepted_documents",
            "required_documents",
            "requires_reacceptance",
            "created_at",
            "updated_at",
        )

    def _build_snapshot(self, obj):
        return build_policy_acceptance_snapshot(user=obj.user)

    def get_accepted_documents(self, obj):
        return self._build_snapshot(obj)["accepted_documents"]

    def get_required_documents(self, obj):
        return self._build_snapshot(obj)["required_documents"]

    def get_requires_reacceptance(self, obj):
        return self._build_snapshot(obj)["requires_reacceptance"]


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
    accepted_documents = serializers.SerializerMethodField()
    required_documents = serializers.SerializerMethodField()
    requires_reacceptance = serializers.SerializerMethodField()

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
            "accepted_documents",
            "required_documents",
            "requires_reacceptance",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "cookies_accepted_at",
            "privacy_policy_accepted_at",
            "terms_and_conditions_accepted_at",
            "accepted_documents",
            "required_documents",
            "requires_reacceptance",
            "created_at",
            "updated_at",
        )

    def _build_snapshot(self, obj):
        return build_policy_acceptance_snapshot(anonymous_consent=obj)

    def get_accepted_documents(self, obj):
        return self._build_snapshot(obj)["accepted_documents"]

    def get_required_documents(self, obj):
        return self._build_snapshot(obj)["required_documents"]

    def get_requires_reacceptance(self, obj):
        return self._build_snapshot(obj)["requires_reacceptance"]


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
            raise serializers.ValidationError("identifier and write_token must be provided together.")
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


class RgpdPublicPolicyVersionSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="document.document_type", read_only=True)

    class Meta:
        model = RgpdPolicyVersion
        fields = (
            "type",
            "version",
            "title",
            "body_markdown",
            "published_at",
        )
        read_only_fields = fields


class RgpdDataRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = RgpdDataRequest
        fields = (
            "uuid",
            "request_type",
            "status",
            "details",
            "resolution_notes",
            "submitted_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "status",
            "resolution_notes",
            "submitted_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )


class RgpdDataRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RgpdDataRequest
        fields = (
            "request_type",
            "details",
        )


class RegisterRgpdSerializer(serializers.Serializer):
    privacy_policy_accepted = serializers.BooleanField()
    terms_and_conditions_accepted = serializers.BooleanField()
    cookies_accepted = serializers.BooleanField(required=False, default=False)
    source = serializers.CharField(required=False, allow_blank=True, max_length=64)

    def validate(self, attrs):
        missing_types = get_missing_required_policy_types()
        if missing_types:
            raise serializers.ValidationError({"non_field_errors": ["Required RGPD policies are not published yet."]})

        for document_type in REQUIRED_POLICY_TYPES:
            field_name = f"{document_type}_accepted"
            if attrs.get(field_name) is not True:
                raise serializers.ValidationError({field_name: ["This policy must be accepted."]})
        return attrs


class ManagementRgpdPolicyDocumentSerializer(serializers.ModelSerializer):
    current_version = serializers.SerializerMethodField()

    class Meta:
        model = RgpdPolicyDocument
        fields = (
            "uuid",
            "document_type",
            "current_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_current_version(self, obj):
        version = obj.versions.filter(is_current=True, is_published=True).first()
        if version is None:
            return None
        return {
            "uuid": str(version.uuid),
            "version": version.version,
            "title": version.title,
            "published_at": (
                version.published_at.isoformat().replace("+00:00", "Z") if version.published_at is not None else None
            ),
        }


class ManagementRgpdPolicyVersionSerializer(serializers.ModelSerializer):
    document_type = serializers.CharField(source="document.document_type", read_only=True)
    document_uuid = serializers.UUIDField(source="document.uuid", read_only=True)

    class Meta:
        model = RgpdPolicyVersion
        fields = (
            "uuid",
            "document_uuid",
            "document_type",
            "version",
            "title",
            "body_markdown",
            "is_published",
            "is_current",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "document_uuid",
            "document_type",
            "is_published",
            "is_current",
            "published_at",
            "created_at",
            "updated_at",
        )


class ManagementRgpdPolicyVersionCreateSerializer(serializers.ModelSerializer):
    document_type = serializers.ChoiceField(choices=RgpdPolicyDocument.DocumentType.choices)

    class Meta:
        model = RgpdPolicyVersion
        fields = (
            "document_type",
            "version",
            "title",
            "body_markdown",
        )

    def create(self, validated_data):
        document_type = validated_data.pop("document_type")
        document = RgpdPolicyDocument.objects.get(document_type=document_type)
        return RgpdPolicyVersion.objects.create(document=document, **validated_data)


class ManagementRgpdDataRequestSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    resolved_by_email = serializers.EmailField(source="resolved_by.email", read_only=True, allow_null=True)

    class Meta:
        model = RgpdDataRequest
        fields = (
            "uuid",
            "user",
            "user_email",
            "request_type",
            "status",
            "details",
            "resolution_notes",
            "resolved_by",
            "resolved_by_email",
            "submitted_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "user",
            "user_email",
            "resolved_by",
            "resolved_by_email",
            "submitted_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )


class ManagementRgpdDataRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RgpdDataRequest
        fields = (
            "status",
            "resolution_notes",
        )
