from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed demo data (disabled: jobs app has been removed)"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "seed_demo_data command is disabled. The jobs app has been removed from the project."
            )
        )
