import uuid

from django.db import models


class Category(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AllowedCity(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ServiceCatalog(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    category = models.ForeignKey(
        "organization.Category",
        on_delete=models.PROTECT,
        related_name="service_catalogs",
    )
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PlanTierCatalog(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
