import uuid

from django.conf import settings
from django.db import models


class NotificationTemplate(models.Model):
    class Category(models.TextChoices):
        SYSTEM = "system", "System"
        CHAT = "chat", "Chat"
        MARKETING = "marketing", "Marketing"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Channel(models.TextChoices):
        IN_APP = "in_app", "In app"
        EMAIL = "email", "Email"
        PUSH = "push", "Push"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    title_template = models.CharField(max_length=255)
    body_template = models.TextField()
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.SYSTEM,
    )
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    default_channels = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class Notification(models.Model):
    class Origin(models.TextChoices):
        SYSTEM = "system", "System"
        MANAGEMENT = "management", "Management"
        JOB_CHAT = "job_chat", "Job chat"
        COMMUNICATION = "communication", "Communication"

    class Category(models.TextChoices):
        SYSTEM = "system", "System"
        CHAT = "chat", "Chat"
        MARKETING = "marketing", "Marketing"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class TargetType(models.TextChoices):
        USER = "user", "User"
        ORGANIZATION = "organization", "Organization"
        BROADCAST = "broadcast", "Broadcast"

    class Channel(models.TextChoices):
        IN_APP = "in_app", "In app"
        EMAIL = "email", "Email"
        PUSH = "push", "Push"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    template = models.ForeignKey(
        NotificationTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_notifications",
    )
    origin = models.CharField(
        max_length=20,
        choices=Origin.choices,
        default=Origin.SYSTEM,
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.SYSTEM,
    )
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    target_type = models.CharField(
        max_length=20,
        choices=TargetType.choices,
        default=TargetType.USER,
    )
    target_label = models.CharField(max_length=255, blank=True)
    target_uuid = models.UUIDField(null=True, blank=True)
    title = models.CharField(max_length=255)
    body = models.TextField()
    action_url = models.CharField(max_length=255, blank=True)
    requested_channels = models.JSONField(default=list, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["origin", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
            models.Index(fields=["target_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.origin}:{self.title}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    system_notifications = models.BooleanField(default=True)
    chat_notifications = models.BooleanField(default=True)
    marketing_notifications = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self):
        return f"notification-preferences:{self.user_id}"


class NotificationRecipient(models.Model):
    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"
        NOT_CONFIGURED = "not_configured", "Not configured"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="recipients",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_recipients",
    )
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=False)
    push_enabled = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    email_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.SKIPPED,
    )
    push_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.NOT_CONFIGURED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-notification__created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "user"],
                name="notifications_unique_notification_user",
            )
        ]
        indexes = [
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["notification", "user"]),
        ]

    def __str__(self):
        return f"{self.notification_id}:{self.user_id}"


class NotificationDispatch(models.Model):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In app"
        EMAIL = "email", "Email"
        PUSH = "push", "Push"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"
        NOT_CONFIGURED = "not_configured", "Not configured"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    recipient = models.ForeignKey(
        NotificationRecipient,
        on_delete=models.CASCADE,
        related_name="dispatches",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempted_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-attempted_at", "-id"]
        indexes = [
            models.Index(fields=["channel", "-attempted_at"]),
            models.Index(fields=["status", "-attempted_at"]),
        ]

    def __str__(self):
        return f"{self.channel}:{self.status}:{self.recipient_id}"

