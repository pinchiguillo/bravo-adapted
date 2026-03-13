import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("jobs", "0002_jobchat_uuid"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="JobChat",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "job",
                            models.OneToOneField(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="chat",
                                to="jobs.job",
                            ),
                        ),
                    ],
                    options={
                        "ordering": ["-created_at", "-id"],
                        "db_table": "jobs_jobchat",
                    },
                ),
                migrations.CreateModel(
                    name="JobChatMessage",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                        ("content", models.TextField(blank=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "chat",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="messages",
                                to="job_chat.jobchat",
                            ),
                        ),
                        (
                            "sender",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="job_chat_messages",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "ordering": ["created_at", "id"],
                        "db_table": "jobs_jobchatmessage",
                    },
                ),
                migrations.CreateModel(
                    name="JobChatAttachment",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("file", models.FileField(upload_to="job-chat-attachments/%Y/%m/%d/")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "message",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="attachments",
                                to="job_chat.jobchatmessage",
                            ),
                        ),
                        (
                            "uploaded_by",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="job_chat_attachments",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "ordering": ["created_at", "id"],
                        "db_table": "jobs_jobchatattachment",
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
