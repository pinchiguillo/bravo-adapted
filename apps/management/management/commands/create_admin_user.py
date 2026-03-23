from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

ADMIN_EMAIL = "admin@bravo.example.com"
ADMIN_PASSWORD = "change-me-admin-password"
ADMIN_USERNAME = "admin"


class Command(BaseCommand):
    help = "Creates or updates the default administrator account."

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            email=ADMIN_EMAIL,
            defaults={
                "username": ADMIN_USERNAME,
            },
        )

        user.is_staff = True
        user.is_superuser = True
        if not user.username:
            user.username = ADMIN_USERNAME
        user.set_password(ADMIN_PASSWORD)
        user.save()

        status_message = "created" if created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Admin user {status_message}: {ADMIN_EMAIL}"
            )
        )
