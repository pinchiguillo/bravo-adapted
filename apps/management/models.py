import uuid

from django.db import models


class FeatureFlag(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key
