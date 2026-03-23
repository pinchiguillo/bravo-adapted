from django.conf import settings
from django.db import models
from django.utils import timezone


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
