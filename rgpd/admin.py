from django.contrib import admin

from .models import (
    RgpdAnonymousConsent,
    RgpdAnonymousConsentEvent,
    RgpdConsent,
    RgpdConsentEvent,
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
