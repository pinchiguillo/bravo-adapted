import os
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .storage import LegalDocumentsStorage

legal_documents_storage = LegalDocumentsStorage()


def legal_document_upload_to(instance, filename):
    extension = Path(filename or "").suffix.lower()
    user_uuid = getattr(instance.user, "uuid", None) or instance.user_id
    date_prefix = timezone.now().strftime("%Y/%m/%d")
    object_name = f"{uuid.uuid4().hex}{extension}"
    return f"{settings.LEGAL_DOCUMENTS_UPLOAD_PREFIX}/users/{user_uuid}/{date_prefix}/{object_name}"


class BaseRgpdConsent(models.Model):
    cookies_accepted = models.BooleanField(default=False)
    cookies_accepted_at = models.DateTimeField(blank=True, null=True)
    cookies_version = models.CharField(max_length=64, blank=True)
    privacy_policy_accepted = models.BooleanField(default=False)
    privacy_policy_accepted_at = models.DateTimeField(blank=True, null=True)
    privacy_policy_version = models.CharField(max_length=64, blank=True)
    terms_and_conditions_accepted = models.BooleanField(default=False)
    terms_and_conditions_accepted_at = models.DateTimeField(blank=True, null=True)
    terms_and_conditions_version = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def apply_acceptance_changes(self, validated_data):
        self._apply_acceptance(
            "cookies_accepted",
            "cookies_accepted_at",
            validated_data,
        )
        self._apply_acceptance(
            "privacy_policy_accepted",
            "privacy_policy_accepted_at",
            validated_data,
        )
        self._apply_acceptance(
            "terms_and_conditions_accepted",
            "terms_and_conditions_accepted_at",
            validated_data,
        )

        for field in (
            "cookies_version",
            "privacy_policy_version",
            "terms_and_conditions_version",
            "source",
            "ip_address",
            "user_agent",
        ):
            if field in validated_data:
                setattr(self, field, validated_data[field])

    def _apply_acceptance(self, boolean_field, datetime_field, validated_data):
        if boolean_field not in validated_data:
            return

        accepted = validated_data[boolean_field]
        setattr(self, boolean_field, accepted)
        setattr(self, datetime_field, timezone.now() if accepted else None)

    def build_event_payload(self):
        return {
            "cookies_accepted": self.cookies_accepted,
            "cookies_accepted_at": self.cookies_accepted_at,
            "cookies_version": self.cookies_version,
            "privacy_policy_accepted": self.privacy_policy_accepted,
            "privacy_policy_accepted_at": self.privacy_policy_accepted_at,
            "privacy_policy_version": self.privacy_policy_version,
            "terms_and_conditions_accepted": self.terms_and_conditions_accepted,
            "terms_and_conditions_accepted_at": self.terms_and_conditions_accepted_at,
            "terms_and_conditions_version": self.terms_and_conditions_version,
            "source": self.source,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


class BaseRgpdConsentEvent(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPSERT = "upsert", "Upsert"
        UPDATE = "update", "Update"

    action = models.CharField(max_length=16, choices=Action.choices)
    cookies_accepted = models.BooleanField(default=False)
    cookies_accepted_at = models.DateTimeField(blank=True, null=True)
    cookies_version = models.CharField(max_length=64, blank=True)
    privacy_policy_accepted = models.BooleanField(default=False)
    privacy_policy_accepted_at = models.DateTimeField(blank=True, null=True)
    privacy_policy_version = models.CharField(max_length=64, blank=True)
    terms_and_conditions_accepted = models.BooleanField(default=False)
    terms_and_conditions_accepted_at = models.DateTimeField(blank=True, null=True)
    terms_and_conditions_version = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class RgpdConsent(BaseRgpdConsent):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rgpd_consent",
    )

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "RGPD consent"
        verbose_name_plural = "RGPD consents"

    def __str__(self):
        return f"rgpd:{self.user_id}"


class RgpdAnonymousConsent(BaseRgpdConsent):
    identifier = models.CharField(max_length=128, unique=True)
    write_token_hash = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "RGPD anonymous consent"
        verbose_name_plural = "RGPD anonymous consents"

    def __str__(self):
        return f"rgpd-anonymous:{self.identifier}"


class RgpdConsentEvent(BaseRgpdConsentEvent):
    consent = models.ForeignKey(
        RgpdConsent,
        on_delete=models.CASCADE,
        related_name="events",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "RGPD consent event"
        verbose_name_plural = "RGPD consent events"

    def __str__(self):
        return f"{self.action} consent event for {self.consent_id}"


class RgpdAnonymousConsentEvent(BaseRgpdConsentEvent):
    consent = models.ForeignKey(
        RgpdAnonymousConsent,
        on_delete=models.CASCADE,
        related_name="events",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "RGPD anonymous consent event"
        verbose_name_plural = "RGPD anonymous consent events"

    def __str__(self):
        return f"{self.action} consent event for {self.consent_id}"


class RgpdLegalDocument(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rgpd_legal_documents",
    )
    document_type = models.CharField(max_length=64)
    file = models.FileField(
        upload_to=legal_document_upload_to,
        storage=legal_documents_storage,
    )
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "RGPD legal document"
        verbose_name_plural = "RGPD legal documents"

    def __str__(self):
        filename = os.path.basename(self.file.name or "")
        return f"rgpd-legal-document:{self.user_id}:{filename}"


class RgpdPolicyDocument(models.Model):
    class DocumentType(models.TextChoices):
        PRIVACY_POLICY = "privacy_policy", "Privacy policy"
        TERMS_AND_CONDITIONS = "terms_and_conditions", "Terms and conditions"
        COOKIES_POLICY = "cookies_policy", "Cookies policy"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    document_type = models.CharField(max_length=64, choices=DocumentType.choices, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_type", "id"]
        verbose_name = "RGPD policy document"
        verbose_name_plural = "RGPD policy documents"

    def __str__(self):
        return self.document_type


class RgpdPolicyVersion(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    document = models.ForeignKey(
        RgpdPolicyDocument,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    body_markdown = models.TextField()
    is_published = models.BooleanField(default=False)
    is_current = models.BooleanField(default=False)
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document__document_type", "-published_at", "-created_at", "-id"]
        verbose_name = "RGPD policy version"
        verbose_name_plural = "RGPD policy versions"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "version"],
                name="rgpd_unique_policy_version_per_document",
            ),
            models.UniqueConstraint(
                fields=["document"],
                condition=Q(is_current=True),
                name="rgpd_single_current_policy_version_per_document",
            ),
        ]

    def __str__(self):
        return f"{self.document.document_type}:{self.version}"


class RgpdPolicyAcceptance(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rgpd_policy_acceptances",
        blank=True,
        null=True,
    )
    anonymous_consent = models.ForeignKey(
        RgpdAnonymousConsent,
        on_delete=models.CASCADE,
        related_name="policy_acceptances",
        blank=True,
        null=True,
    )
    policy_version = models.ForeignKey(
        RgpdPolicyVersion,
        on_delete=models.CASCADE,
        related_name="acceptances",
    )
    source = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    accepted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accepted_at", "-id"]
        verbose_name = "RGPD policy acceptance"
        verbose_name_plural = "RGPD policy acceptances"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(user__isnull=False) & Q(anonymous_consent__isnull=True))
                    | (Q(user__isnull=True) & Q(anonymous_consent__isnull=False))
                ),
                name="rgpd_policy_acceptance_requires_single_subject",
            ),
        ]

    def __str__(self):
        subject = self.user_id or self.anonymous_consent_id
        return f"rgpd-policy-acceptance:{subject}:{self.policy_version_id}"


class RgpdDataRequest(models.Model):
    class RequestType(models.TextChoices):
        ACCESS = "access", "Access"
        RECTIFICATION = "rectification", "Rectification"
        ERASURE = "erasure", "Erasure"
        PORTABILITY = "portability", "Portability"
        RESTRICTION = "restriction", "Restriction"
        OBJECTION = "objection", "Objection"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        IN_REVIEW = "in_review", "In review"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rgpd_data_requests",
    )
    request_type = models.CharField(max_length=32, choices=RequestType.choices)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    details = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="resolved_rgpd_data_requests",
        blank=True,
        null=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        verbose_name = "RGPD data request"
        verbose_name_plural = "RGPD data requests"

    def __str__(self):
        return f"rgpd-data-request:{self.user_id}:{self.request_type}:{self.status}"
