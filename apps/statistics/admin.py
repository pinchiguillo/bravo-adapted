from django.contrib import admin

from .models import DailyAnnouncementStats, DailyPlatformStats


@admin.register(DailyPlatformStats)
class DailyPlatformStatsAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "new_users",
        "active_users",
        "new_announcements",
        "announcement_views",
        "new_jobs",
        "new_job_chat_messages",
    )
    ordering = ("-date",)


@admin.register(DailyAnnouncementStats)
class DailyAnnouncementStatsAdmin(admin.ModelAdmin):
    list_display = ("date", "announcement", "views")
    list_select_related = ("announcement",)
    ordering = ("-date", "-views")
