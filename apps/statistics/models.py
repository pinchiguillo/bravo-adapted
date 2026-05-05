from django.db import models


class DailyPlatformStats(models.Model):
    date = models.DateField(unique=True)
    new_users = models.PositiveIntegerField(default=0)
    active_users = models.PositiveIntegerField(default=0)
    new_organizations = models.PositiveIntegerField(default=0)
    new_announcements = models.PositiveIntegerField(default=0)
    announcement_favorites = models.PositiveIntegerField(default=0)
    new_jobs = models.PositiveIntegerField(default=0)
    new_job_chats = models.PositiveIntegerField(default=0)
    new_job_chat_messages = models.PositiveIntegerField(default=0)
    announcement_views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date",)

    def __str__(self):
        return f"DailyPlatformStats({self.date})"


class DailyAnnouncementStats(models.Model):
    announcement = models.ForeignKey(
        "organization.Announcement",
        on_delete=models.CASCADE,
        related_name="daily_stats",
    )
    date = models.DateField()
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-views", "announcement_id")
        constraints = [
            models.UniqueConstraint(
                fields=("announcement", "date"),
                name="statistics_unique_daily_announcement_stats",
            )
        ]

    def __str__(self):
        return f"DailyAnnouncementStats({self.announcement_id}, {self.date})"

