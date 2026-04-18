import uuid

from django.conf import settings
from django.db import models


class JobChat(models.Model):
    """Chat thread associated with a Job."""

    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)
    job = models.OneToOneField("jobs.Job", on_delete=models.CASCADE, related_name="chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "job_chat_jobchat"
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["job"]),
        ]

    def __str__(self):
        return f"Chat for Job {self.job.uuid}"


class JobChatMessage(models.Model):
    """Message in a JobChat thread."""

    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)
    job_chat = models.ForeignKey(JobChat, on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_chat_messages")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "job_chat_jobchatmessage"
        indexes = [
            models.Index(fields=["job_chat", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"Message {self.uuid} in {self.job_chat.uuid}"


class JobChatAttachment(models.Model):
    """Attachment in a JobChatMessage, backed by an Asset in S3."""

    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)
    message = models.ForeignKey(
        JobChatMessage, on_delete=models.CASCADE, related_name="attachments"
    )
    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.PROTECT,
        related_name="job_chat_attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "job_chat_jobchatattachment"
        indexes = [
            models.Index(fields=["message"]),
        ]

    def __str__(self):
        return f"Attachment {self.uuid}"
