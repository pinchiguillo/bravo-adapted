from django.contrib import admin

from .models import (
    RgpdAnonymousConsent,
    RgpdAnonymousConsentEvent,
    RgpdConsent,
    RgpdConsentEvent,
    RgpdDataRequest,
    RgpdPolicyAcceptance,
    RgpdPolicyDocument,
    RgpdPolicyVersion,
)


@admin.register(RgpdConsent)
class RgpdConsentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cookies_accepted",
        "privacy_policy_accepted",
        "terms_and_conditions_accepted",
        "updated_at",
    )
    search_fields = ("user__email", "user__username", "source", "ip_address")


@admin.register(RgpdAnonymousConsent)
class RgpdAnonymousConsentAdmin(admin.ModelAdmin):
    list_display = (
        "identifier",
        "cookies_accepted",
        "privacy_policy_accepted",
        "terms_and_conditions_accepted",
        "updated_at",
    )
    search_fields = ("identifier", "source", "ip_address")


@admin.register(RgpdConsentEvent)
class RgpdConsentEventAdmin(admin.ModelAdmin):
    list_display = ("consent", "action", "source", "ip_address", "created_at")
    search_fields = ("consent__user__email", "consent__user__username", "source", "ip_address")


@admin.register(RgpdAnonymousConsentEvent)
class RgpdAnonymousConsentEventAdmin(admin.ModelAdmin):
    list_display = ("consent", "action", "source", "ip_address", "created_at")
    search_fields = ("consent__identifier", "source", "ip_address")


@admin.register(RgpdPolicyDocument)
class RgpdPolicyDocumentAdmin(admin.ModelAdmin):
    list_display = ("document_type", "updated_at")
    search_fields = ("document_type",)


@admin.register(RgpdPolicyVersion)
class RgpdPolicyVersionAdmin(admin.ModelAdmin):
    list_display = ("document", "version", "title", "is_published", "is_current", "published_at")
    list_filter = ("document__document_type", "is_published", "is_current")
    search_fields = ("document__document_type", "version", "title")


@admin.register(RgpdPolicyAcceptance)
class RgpdPolicyAcceptanceAdmin(admin.ModelAdmin):
    list_display = ("policy_version", "user", "anonymous_consent", "source", "accepted_at")
    list_filter = ("policy_version__document__document_type",)
    search_fields = ("user__email", "anonymous_consent__identifier", "source", "ip_address")


@admin.register(RgpdDataRequest)
class RgpdDataRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "request_type", "status", "submitted_at", "resolved_at")
    list_filter = ("request_type", "status")
    search_fields = ("user__email", "details", "resolution_notes")
