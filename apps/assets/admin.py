from django.contrib import admin

from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "visibility", "status", "owner", "original_filename", "created_at")
    list_filter = ("kind", "visibility", "status", "is_temporary")
    search_fields = ("id", "original_filename", "owner__username", "draft_token")
    readonly_fields = ("id", "created_at", "uploaded_at", "confirmed_at")
