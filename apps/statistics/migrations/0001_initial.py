from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organization", "0015_announcementfavorite"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyPlatformStats",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(unique=True)),
                ("new_users", models.PositiveIntegerField(default=0)),
                ("active_users", models.PositiveIntegerField(default=0)),
                ("new_organizations", models.PositiveIntegerField(default=0)),
                ("new_announcements", models.PositiveIntegerField(default=0)),
                ("announcement_favorites", models.PositiveIntegerField(default=0)),
                ("new_jobs", models.PositiveIntegerField(default=0)),
                ("new_job_chats", models.PositiveIntegerField(default=0)),
                ("new_job_chat_messages", models.PositiveIntegerField(default=0)),
                ("announcement_views", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("-date",)},
        ),
        migrations.CreateModel(
            name="DailyAnnouncementStats",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("views", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "announcement",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="daily_stats",
                        to="organization.announcement",
                    ),
                ),
            ],
            options={"ordering": ("-date", "-views", "announcement_id")},
        ),
        migrations.AddConstraint(
            model_name="dailyannouncementstats",
            constraint=models.UniqueConstraint(
                fields=("announcement", "date"),
                name="statistics_unique_daily_announcement_stats",
            ),
        ),
    ]
