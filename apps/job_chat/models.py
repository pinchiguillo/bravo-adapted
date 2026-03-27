import uuid

from django.conf import settings
from django.db import models

from apps.jobs.models import Job


class JobChat(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        db_table = "jobs_jobchat"

    def __str__(self):
        return f"chat:{self.uuid}"


class JobChatMessage(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    chat = models.ForeignKey(JobChat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_chat_messages",
    )
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        db_table = "jobs_jobchatmessage"

    def __str__(self):
        return f"{self.chat_id}:{self.sender_id}:{self.id}"


class JobChatAttachment(models.Model):
    message = models.ForeignKey(
        JobChatMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="job-chat-attachments/%Y/%m/%d/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_chat_attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        db_table = "jobs_jobchatattachment"

    def __str__(self):
        return f"{self.message_id}:{self.id}"
