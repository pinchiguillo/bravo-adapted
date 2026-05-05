from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organization", "0015_announcementfavorite"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("in_app_enabled", models.BooleanField(default=True)),
                ("email_enabled", models.BooleanField(default=True)),
                ("push_enabled", models.BooleanField(default=False)),
                ("system_notifications", models.BooleanField(default=True)),
                ("chat_notifications", models.BooleanField(default=True)),
                ("marketing_notifications", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="notification_preferences", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["user_id"]},
        ),
        migrations.CreateModel(
            name="NotificationTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("key", models.SlugField(max_length=100, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("title_template", models.CharField(max_length=255)),
                ("body_template", models.TextField()),
                ("category", models.CharField(choices=[("system", "System"), ("chat", "Chat"), ("marketing", "Marketing")], default="system", max_length=20)),
                ("severity", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=20)),
                ("default_channels", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("origin", models.CharField(choices=[("system", "System"), ("management", "Management"), ("job_chat", "Job chat"), ("communication", "Communication")], default="system", max_length=20)),
                ("category", models.CharField(choices=[("system", "System"), ("chat", "Chat"), ("marketing", "Marketing")], default="system", max_length=20)),
                ("severity", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=20)),
                ("target_type", models.CharField(choices=[("user", "User"), ("organization", "Organization"), ("broadcast", "Broadcast")], default="user", max_length=20)),
                ("target_label", models.CharField(blank=True, max_length=255)),
                ("target_uuid", models.UUIDField(blank=True, null=True)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("action_url", models.CharField(blank=True, max_length=255)),
                ("requested_channels", models.JSONField(blank=True, default=list)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_notifications", to=settings.AUTH_USER_MODEL)),
                ("template", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to="notifications.notificationtemplate")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="NotificationRecipient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("in_app_enabled", models.BooleanField(default=True)),
                ("email_enabled", models.BooleanField(default=False)),
                ("push_enabled", models.BooleanField(default=False)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("email_status", models.CharField(choices=[("pending", "Pending"), ("delivered", "Delivered"), ("skipped", "Skipped"), ("failed", "Failed"), ("not_configured", "Not configured")], default="skipped", max_length=20)),
                ("push_status", models.CharField(choices=[("pending", "Pending"), ("delivered", "Delivered"), ("skipped", "Skipped"), ("failed", "Failed"), ("not_configured", "Not configured")], default="not_configured", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recipients", to="notifications.notification")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_recipients", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-notification__created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="NotificationDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("channel", models.CharField(choices=[("in_app", "In app"), ("email", "Email"), ("push", "Push")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("delivered", "Delivered"), ("skipped", "Skipped"), ("failed", "Failed"), ("not_configured", "Not configured")], default="pending", max_length=20)),
                ("attempted_at", models.DateTimeField(auto_now_add=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dispatches", to="notifications.notificationrecipient")),
            ],
            options={"ordering": ["-attempted_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["origin", "-created_at"], name="notifications_origin_created_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["category", "-created_at"], name="notifications_category_created_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["target_type", "-created_at"], name="notifications_target_created_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationrecipient",
            index=models.Index(fields=["user", "read_at"], name="notifications_user_read_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationrecipient",
            index=models.Index(fields=["notification", "user"], name="notifications_notification_user_idx"),
        ),
        migrations.AddConstraint(
            model_name="notificationrecipient",
            constraint=models.UniqueConstraint(fields=("notification", "user"), name="notifications_unique_notification_user"),
        ),
        migrations.AddIndex(
            model_name="notificationdispatch",
            index=models.Index(fields=["channel", "-attempted_at"], name="notifications_dispatch_channel_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationdispatch",
            index=models.Index(fields=["status", "-attempted_at"], name="notifications_dispatch_status_idx"),
        ),
    ]
