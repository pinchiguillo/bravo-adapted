from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0015_announcementfavorite"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationAvailabilitySettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timezone", models.CharField(default="Europe/Madrid", max_length=64)),
                ("is_enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="availability_settings",
                        to="organization.organization",
                    ),
                ),
            ],
            options={"ordering": ["organization_id"]},
        ),
        migrations.CreateModel(
            name="OrganizationAvailabilityException",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("mode", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], max_length=10)),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("label", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "settings",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exceptions",
                        to="organization.organizationavailabilitysettings",
                    ),
                ),
            ],
            options={"ordering": ["date", "start_time", "id"]},
        ),
        migrations.CreateModel(
            name="OrganizationWeeklyAvailability",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("weekday", models.PositiveSmallIntegerField(choices=[(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")])),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "settings",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="weekly_schedule",
                        to="organization.organizationavailabilitysettings",
                    ),
                ),
            ],
            options={"ordering": ["weekday", "start_time", "id"]},
        ),
        migrations.AddIndex(
            model_name="organizationavailabilityexception",
            index=models.Index(fields=["settings", "date", "start_time"], name="organizatio_setting_1c9f58_idx"),
        ),
        migrations.AddIndex(
            model_name="organizationweeklyavailability",
            index=models.Index(fields=["settings", "weekday", "start_time"], name="organizatio_setting_5b2506_idx"),
        ),
    ]
