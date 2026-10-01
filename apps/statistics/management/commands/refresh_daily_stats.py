from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.statistics.services import refresh_daily_platform_stats


class Command(BaseCommand):
    help = "Refresh recent daily internal platform statistics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of trailing days to recompute, including today.",
        )

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=days - 1)
        refresh_daily_platform_stats(start_date, end_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Recent daily platform statistics refreshed for {start_date.isoformat()} to {end_date.isoformat()}."
            )
        )
