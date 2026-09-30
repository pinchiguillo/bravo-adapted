from django.db import models
from rest_framework import serializers


class Currency(models.TextChoices):
    """ISO 4217 currencies the marketplace accepts."""

    EUR = "EUR", "Euro"
    USD = "USD", "US dollar"
    GBP = "GBP", "Pound sterling"


class CurrencyField(serializers.ChoiceField):
    """Accepts a supported currency code in any case and returns it upper-cased."""

    def __init__(self, **kwargs):
        kwargs.setdefault("choices", Currency.choices)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip().upper()
        return super().to_internal_value(data)
