from django.contrib import admin

from .models import (
    Category,
    Organization,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "billing_email", "billing_country", "created_at")
    search_fields = ("name", "legal_name", "tax_id", "billing_email", "user__email")


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
