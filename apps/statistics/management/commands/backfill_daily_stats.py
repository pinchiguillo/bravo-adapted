from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.statistics.services import refresh_daily_platform_stats


class Command(BaseCommand):
    help = "Backfill or recompute daily internal platform statistics for a date range."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="from_date", required=False)
        parser.add_argument("--to", dest="to_date", required=False)

    def handle(self, *args, **options):
        start_date = self._parse_date(options.get("from_date")) or timezone.localdate()
        end_date = self._parse_date(options.get("to_date")) or timezone.localdate()
        if start_date > end_date:
            raise CommandError("--from must be earlier than or equal to --to.")
        refresh_daily_platform_stats(start_date, end_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Daily platform statistics refreshed for {start_date.isoformat()} to {end_date.isoformat()}."
            )
        )

    def _parse_date(self, raw_value):
        if not raw_value:
            return None
        try:
            return date.fromisoformat(raw_value)
        except ValueError as exc:
            raise CommandError(f"Invalid date: {raw_value}. Use YYYY-MM-DD.") from exc

