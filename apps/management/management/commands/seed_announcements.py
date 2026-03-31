from django.core.management.base import BaseCommand
from django.db import transaction

from apps.organization.models import Announcement, Category, Organization, Subservice

DEFAULT_CATEGORY_NAME = "General"
DEFAULT_CATEGORY_DESCRIPTION = "Categoria generica para announcements seed."
DEFAULT_ANNOUNCEMENT_SUFFIX = "Servicio destacado"
DEFAULT_FREE_TEXT = "Presupuesto disponible bajo solicitud."


class Command(BaseCommand):
    help = "Seeds announcements for active organizations."

    @transaction.atomic
    def handle(self, *args, **options):
        counters = {
            "categories": 0,
            "announcements_created": 0,
            "announcements_updated": 0,
            "organizations_skipped": 0,
        }

        fallback_category, category_created = Category.objects.get_or_create(
            name=DEFAULT_CATEGORY_NAME,
            defaults={"description": DEFAULT_CATEGORY_DESCRIPTION},
        )
        if category_created:
            counters["categories"] += 1
        elif fallback_category.description != DEFAULT_CATEGORY_DESCRIPTION:
            fallback_category.description = DEFAULT_CATEGORY_DESCRIPTION
            fallback_category.save(update_fields=["description"])

        organizations = Organization.objects.filter(status=Organization.Status.ACTIVE).order_by("id")

        for organization in organizations:
            first_catalog = (
                Subservice.objects.select_related("service_catalog__category")
                .filter(announcement__organization=organization)
                .order_by("id")
                .first()
            )
            category = first_catalog.service_catalog.category if first_catalog else fallback_category
            announcement_name = f"{organization.name} - {DEFAULT_ANNOUNCEMENT_SUFFIX}"
            announcement, created = Announcement.objects.update_or_create(
                organization=organization,
                name=announcement_name,
                defaults={
                    "category": category,
                    "location": organization.billing_city or organization.billing_country,
                    "announcement": f"Servicios disponibles de {organization.name}.",
                    "status": Announcement.Status.ACTIVE,
                    "description": (
                        f"Announcement generado por seed para {organization.name} "
                        f"en {organization.billing_city or organization.billing_country}."
                    ),
                    "free_text": DEFAULT_FREE_TEXT,
                    "latitude": None,
                    "longitude": None,
                },
            )

            if created:
                counters["announcements_created"] += 1
            else:
                counters["announcements_updated"] += 1

        if not organizations.exists():
            counters["organizations_skipped"] += 1
            self.stdout.write(
                self.style.WARNING("No active organizations found. No announcements were created.")
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Announcement seed completed "
                f"(categories={counters['categories']}, "
                f"announcements_created={counters['announcements_created']}, "
                f"announcements_updated={counters['announcements_updated']}, "
                f"organizations_skipped={counters['organizations_skipped']})."
            )
        )
