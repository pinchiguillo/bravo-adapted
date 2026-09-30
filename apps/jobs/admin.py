from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("uuid", "user", "announcement", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("uuid", "user__email", "announcement__name")
    raw_id_fields = ("user", "announcement", "plan_price")
