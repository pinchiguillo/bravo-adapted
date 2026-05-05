from django.contrib import admin

from .models import (
    Category,
    Organization,
    OrganizationAvailabilityException,
    OrganizationAvailabilitySettings,
    OrganizationPricing,
    OrganizationWeeklyAvailability,
    PlanTierCatalog,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "billing_email", "billing_country", "created_at")
    search_fields = ("name", "legal_name", "tax_id", "billing_email", "user__email")


@admin.register(OrganizationPricing)
class OrganizationPricingAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "plan_tier",
        "monthly_price",
        "commission_rate",
        "currency",
        "updated_at",
    )
    list_filter = ("plan_tier", "currency")
    search_fields = ("organization__name", "organization__legal_name", "organization__user__email")


@admin.register(OrganizationAvailabilitySettings)
class OrganizationAvailabilitySettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "timezone", "is_enabled", "updated_at")
    list_filter = ("is_enabled", "timezone")
    search_fields = ("organization__name", "organization__user__email", "timezone")


@admin.register(OrganizationWeeklyAvailability)
class OrganizationWeeklyAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("settings", "weekday", "start_time", "end_time")
    list_filter = ("weekday",)
    search_fields = ("settings__organization__name", "settings__organization__user__email")


@admin.register(OrganizationAvailabilityException)
class OrganizationAvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ("settings", "date", "mode", "start_time", "end_time", "label")
    list_filter = ("mode", "date")
    search_fields = ("settings__organization__name", "settings__organization__user__email", "label")


@admin.register(PlanTierCatalog)
class PlanTierCatalogAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "sort_order")
    list_filter = ("sort_order",)
    search_fields = ("key", "name")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "uuid")
    search_fields = ("name",)


@admin.register(ServiceCatalog)
class ServiceCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "created_at")
    search_fields = ("name", "category__name")


@admin.register(Subservice)
class SubserviceAdmin(admin.ModelAdmin):
    list_display = ("announcement", "service_catalog", "name", "created_at")
    search_fields = ("announcement__name", "service_catalog__name", "name")


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ("subservice", "amount", "currency", "effective_from", "effective_to")
    list_filter = ("currency",)
    search_fields = (
        "subservice__name",
        "subservice__service_catalog__name",
        "subservice__announcement__organization__name",
    )
