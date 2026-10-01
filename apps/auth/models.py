import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)  # noqa: DJ001 - null means "never provided" in the API
    birthdate = models.DateField(blank=True, null=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    email_verified = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    @classmethod
    def email_verification_bypassed(cls):
        return settings.AUTH_BYPASS_EMAIL_VERIFICATION

    @property
    def is_email_verified(self):
        return self.email_verification_bypassed() or self.email_verified

    def mark_email_verified(self):
        if self.email_verified:
            return
        self.email_verified = True
        self.save(update_fields=["email_verified"])
