import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

ADMIN_USERNAME = "admin"


class Command(BaseCommand):
    help = (
        "Creates or updates a local development superuser from DJANGO_SUPERUSER_EMAIL "
        "and DJANGO_SUPERUSER_PASSWORD. Refuses to run in production."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.IS_PRODUCTION:
            raise CommandError("create_admin_user is a development helper; use 'createsuperuser' in production.")

        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")
        if not email or not password:
            raise CommandError("Set DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD before running this command.")

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            email=email,
            defaults={
                "username": ADMIN_USERNAME,
            },
        )

        user.is_staff = True
        user.is_superuser = True
        if not user.username:
            user.username = ADMIN_USERNAME
        user.set_password(password)
        user.save()

        status_message = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Admin user {status_message}: {email}"))
