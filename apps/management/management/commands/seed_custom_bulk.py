from datetime import date
from random import randint, choice

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.organization.models import (
    Announcement,
    Category,
    Organization,
    OrganizationJob,
    Service,
    ServicePrice,
    Subservice,
)

DEFAULT_PASSWORD = "change-me-admin-password"
DEFAULT_PRICE_DATE = date(2026, 1, 1)

CATEGORIES = [
    {"name": "Reformas", "description": "Servicios vinculados a reformas y obras."},
    {"name": "Mantenimiento", "description": "Servicios recurrentes de mantenimiento."},
    {"name": "Limpieza", "description": "Servicios de limpieza profesional."},
    {"name": "Fontanería", "description": "Servicios de fontanería y tuberías."},
    {"name": "Electricidad", "description": "Trabajos eléctricos y mantenimiento."},
]

SERVICES = [
    {"name": "Pintura", "description": "Trabajos de pintura interior y exterior."},
    {"name": "Electricidad", "description": "Instalaciones y reparaciones eléctricas."},
    {"name": "Fontanería", "description": "Reparaciones y renovaciones de fontanería."},
    {"name": "Limpieza", "description": "Servicios de limpieza profesional."},
    {"name": "Carpintería", "description": "Trabajos de carpintería e instalaciones."},
]

CITIES = [
    "Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao",
    "Alicante", "Murcia", "Córdoba", "Valladolid", "Zaragoza",
]


class Command(BaseCommand):
    help = "Seeds bulk custom data: 30 users, 20 organizations, 200 announcements."

    @transaction.atomic
    def handle(self, *args, **options):
        counters = {
            "users": 0,
            "organizations": 0,
            "announcements": 0,
            "categories": 0,
        }

        self.stdout.write("Creating categories...")
        categories_by_name = self._seed_categories(counters)

        self.stdout.write("Creating users...")
        users_by_email = self._seed_users(30, counters)

        self.stdout.write("Creating organizations...")
        organizations = self._seed_organizations(20, users_by_email, categories_by_name, counters)

        self.stdout.write("Creating announcements...")
        self._seed_announcements(200, organizations, categories_by_name, counters)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed completed: {counters['users']} users, "
                f"{counters['organizations']} organizations, "
                f"{counters['announcements']} announcements. "
                f"All user passwords: '{DEFAULT_PASSWORD}'"
            )
        )

    def _seed_categories(self, counters):
        categories_by_name = {}
        for category_data in CATEGORIES:
            category, created = Category.objects.get_or_create(
                name=category_data["name"],
                defaults={"description": category_data["description"]},
            )
            categories_by_name[category_data["name"]] = category
            if created:
                counters["categories"] += 1
        return categories_by_name

    def _seed_users(self, count, counters):
        user_model = get_user_model()
        users_by_email = {}

        for i in range(count):
            email = f"user{i:03d}@seed.local"
            username = f"user{i:03d}"
            defaults = {
                "username": username,
                "first_name": f"User{i}",
                "last_name": f"Seed{i}",
                "email_verified": True,
                "status": user_model.Status.ACTIVE,
            }
            user, created = user_model.objects.update_or_create(
                email=email,
                defaults=defaults,
            )
            user.set_password(DEFAULT_PASSWORD)
            user.save(update_fields=["password"])
            users_by_email[email] = user
            if created:
                counters["users"] += 1

        return users_by_email

    def _seed_organizations(self, count, users_by_email, categories_by_name, counters):
        organizations = []
        user_list = list(users_by_email.values())

        for i in range(count):
            owner = user_list[i % len(user_list)]
            org_name = f"Organization {i:03d}"
            organization_defaults = {
                "name": org_name,
                "legal_name": f"{org_name} SL",
                "tax_id": f"TAX-{i:06d}",
                "billing_email": f"billing{i}@seed.local",
                "billing_address": f"Calle {choice(['Mayor', 'Principal', 'Central', 'del Puerto'])} {randint(1, 99)}",
                "billing_city": choice(CITIES),
                "billing_country": "ES",
                "billing_postal_code": f"{28000 + i:05d}",
                "verification_level": randint(1, 3),
                "is_approved": choice([True, False]),
                "status": Organization.Status.ACTIVE,
            }
            organization, created = Organization.objects.get_or_create(
                user=owner,
                name=org_name,
                defaults=organization_defaults,
            )
            organizations.append(organization)
            if created:
                counters["organizations"] += 1

            # Create default org job and services
            org_job, _ = OrganizationJob.objects.get_or_create(
                organization=organization,
                defaults={
                    "name": f"{org_name} services",
                    "description": f"Services for {org_name}.",
                },
            )

            # Add random services
            for service_data in SERVICES[:randint(2, 4)]:
                category = categories_by_name.get(
                    choice(list(categories_by_name.keys()))
                )
                Service.objects.get_or_create(
                    job=org_job,
                    name=service_data["name"],
                    defaults={
                        "category": category,
                        "description": service_data["description"],
                    },
                )

        return organizations

    def _seed_announcements(self, count, organizations, categories_by_name, counters):
        org_services_cache = {}

        for i in range(count):
            organization = choice(organizations)
            
            if organization.id not in org_services_cache:
                org_job = OrganizationJob.objects.filter(
                    organization=organization
                ).first()
                org_services_cache[organization.id] = (
                    list(org_job.services.all()) if org_job else []
                )

            services = org_services_cache[organization.id]
            if not services:
                continue

            category = categories_by_name.get(
                choice(list(categories_by_name.keys()))
            )
            announcement_name = f"Announcement {i:04d} - {organization.name}"
            announcement, created = Announcement.objects.get_or_create(
                organization=organization,
                name=announcement_name,
                defaults={
                    "category": category,
                    "location": organization.billing_city,
                    "announcement": f"Professional {choice(SERVICES[:3])['name']} services available.",
                    "status": Announcement.Status.ACTIVE,
                    "description": f"Bulk seed announcement {i} for {organization.name}.",
                    "free_text": "Contact for quote.",
                    "latitude": None,
                    "longitude": None,
                },
            )
            if created:
                counters["announcements"] += 1
                announcement.services.set(services[:2])
