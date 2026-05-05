from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models


def _validate_time_range(start_time, end_time):
    if start_time is None or end_time is None:
        return
    if start_time >= end_time:
        raise ValidationError({"end_time": "end_time must be later than start_time."})


def _has_overlap(queryset, start_time, end_time, exclude_pk=None):
    if start_time is None or end_time is None:
        return False

    filters = {
        "start_time__lt": end_time,
        "end_time__gt": start_time,
    }
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.filter(**filters).exists()


class OrganizationAvailabilitySettings(models.Model):
    DEFAULT_TIMEZONE = "Europe/Madrid"

    organization = models.OneToOneField(
        "organization.Organization",
        on_delete=models.CASCADE,
        related_name="availability_settings",
    )
    timezone = models.CharField(max_length=64, default=DEFAULT_TIMEZONE)
    is_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization_id"]

    def __str__(self):
        return f"{self.organization_id}:availability"

    def clean(self):
        super().clean()
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"timezone": "Use a valid IANA timezone."}) from exc


class OrganizationWeeklyAvailability(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    settings = models.ForeignKey(
        OrganizationAvailabilitySettings,
        on_delete=models.CASCADE,
        related_name="weekly_schedule",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["weekday", "start_time", "id"]
        indexes = [
            models.Index(fields=["settings", "weekday", "start_time"]),
        ]

    def __str__(self):
        return f"{self.settings_id}:{self.weekday}:{self.start_time}-{self.end_time}"

    def clean(self):
        super().clean()
        _validate_time_range(self.start_time, self.end_time)
        if self.settings_id and _has_overlap(
            self.settings.weekly_schedule.filter(weekday=self.weekday),
            self.start_time,
            self.end_time,
            exclude_pk=self.pk,
        ):
            raise ValidationError("Weekly availability ranges cannot overlap for the same weekday.")


class OrganizationAvailabilityException(models.Model):
    class Mode(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    settings = models.ForeignKey(
        OrganizationAvailabilitySettings,
        on_delete=models.CASCADE,
        related_name="exceptions",
    )
    date = models.DateField()
    mode = models.CharField(max_length=10, choices=Mode.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time", "id"]
        indexes = [
            models.Index(fields=["settings", "date", "start_time"]),
        ]

    def __str__(self):
        return f"{self.settings_id}:{self.date}:{self.mode}"

    def clean(self):
        super().clean()
        _validate_time_range(self.start_time, self.end_time)
        if self.settings_id and _has_overlap(
            self.settings.exceptions.filter(date=self.date),
            self.start_time,
            self.end_time,
            exclude_pk=self.pk,
        ):
            raise ValidationError("Availability exceptions cannot overlap on the same date.")
