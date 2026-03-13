from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import Job
from organization.models import Organization, Service, ServicePrice, Subservice

DEFAULT_PASSWORD = "change-me-admin-password"
DEFAULT_PRICE_DATE = date(2026, 1, 1)

USERS = [
    {
        "email": "admin.seed@example.com",
        "username": "admin.seed",
        "first_name": "Admin",
        "last_name": "Seed",
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "email": "ana.client@example.com",
        "username": "ana.client",
        "first_name": "Ana",
        "last_name": "Client",
    },
    {
        "email": "bruno.owner@example.com",
        "username": "bruno.owner",
        "first_name": "Bruno",
        "last_name": "Owner",
    },
    {
        "email": "carla.owner@example.com",
        "username": "carla.owner",
        "first_name": "Carla",
        "last_name": "Owner",
    },
]

ORGANIZATIONS = [
    {
        "owner_email": "bruno.owner@example.com",
        "name": "Bravo Reformas",
        "legal_name": "Bravo Reformas SL",
        "tax_id": "BRAVO-001",
        "billing_email": "billing@bravoreformas.example.com",
        "billing_address": "Calle Mayor 10",
        "billing_city": "Madrid",
        "billing_country": "ES",
        "billing_postal_code": "28001",
        "services": [
            {
                "name": "Pintura",
                "description": "Trabajos de pintura interior y exterior.",
                "subservices": [
                    {"name": "Piso completo", "description": "Pintura integral de vivienda.", "amount": "950.00"},
                    {"name": "Habitacion individual", "description": "Pintura de una estancia.", "amount": "180.00"},
                ],
            },
            {
                "name": "Electricidad",
                "description": "Instalaciones y reparaciones electricas.",
                "subservices": [
                    {"name": "Boletin electrico", "description": "Revision y boletin.", "amount": "220.00"},
                    {"name": "Cuadro electrico", "description": "Sustitucion de cuadro.", "amount": "390.00"},
                ],
            },
        ],
    },
    {
        "owner_email": "carla.owner@example.com",
        "name": "Casa Lista",
        "legal_name": "Casa Lista Services SL",
        "tax_id": "CASA-002",
        "billing_email": "billing@casalista.example.com",
        "billing_address": "Avenida del Puerto 20",
        "billing_city": "Valencia",
        "billing_country": "ES",
        "billing_postal_code": "46002",
        "services": [
            {
                "name": "Fontaneria",
                "description": "Reparaciones y renovaciones de fontaneria.",
                "subservices": [
                    {"name": "Fuga urgente", "description": "Reparacion rapida de fuga.", "amount": "140.00"},
                    {"name": "Cambio de griferia", "description": "Sustitucion de grifos.", "amount": "95.00"},
                ],
            },
            {
                "name": "Limpieza",
                "description": "Servicios de limpieza profesional.",
                "subservices": [
                    {"name": "Fin de obra", "description": "Limpieza tras reforma.", "amount": "310.00"},
                    {"name": "Mantenimiento semanal", "description": "Servicio recurrente.", "amount": "85.00"},
                ],
            },
        ],
    },
]

JOBS = [
    {
        "user_email": "ana.client@example.com",
        "organization_name": "Bravo Reformas",
        "service_name": "Pintura",
        "subservice_name": "Piso completo",
        "status": Job.Status.PENDING,
    },
    {
        "user_email": "ana.client@example.com",
        "organization_name": "Bravo Reformas",
        "service_name": "Electricidad",
        "subservice_name": "Cuadro electrico",
        "status": Job.Status.ACTIVE,
    },
    {
        "user_email": "ana.client@example.com",
        "organization_name": "Casa Lista",
        "service_name": "Fontaneria",
        "subservice_name": "Fuga urgente",
        "status": Job.Status.COMPLETED,
    },
    {
        "user_email": "ana.client@example.com",
        "organization_name": "Casa Lista",
        "service_name": "Limpieza",
        "subservice_name": "Fin de obra",
        "status": Job.Status.REJECTED,
    },
]


class Command(BaseCommand):
    help = "Seeds demo users, organizations, services, subservices, prices, and jobs."

    @transaction.atomic
    def handle(self, *args, **options):
        counters = {
            "users": 0,
            "organizations": 0,
            "services": 0,
            "subservices": 0,
            "prices": 0,
            "jobs": 0,
        }
        users_by_email = self._seed_users(counters)
        organizations_by_name = self._seed_organizations(users_by_email, counters)
        self._seed_jobs(users_by_email, organizations_by_name, counters)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed completed "
                f"(created={sum(counters.values())}, "
                f"users={counters['users']}, "
                f"organizations={counters['organizations']}, "
                f"services={counters['services']}, "
                f"subservices={counters['subservices']}, "
                f"prices={counters['prices']}, "
                f"jobs={counters['jobs']}). "
                f"All seeded user passwords are '{DEFAULT_PASSWORD}'."
            )
        )

    def _seed_users(self, counters):
        user_model = get_user_model()
        users_by_email = {}

        for user_data in USERS:
            email = user_data["email"]
            defaults = {
                "username": user_data["username"],
                "first_name": user_data["first_name"],
                "last_name": user_data["last_name"],
                "is_staff": user_data.get("is_staff", False),
                "is_superuser": user_data.get("is_superuser", False),
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

    def _seed_organizations(self, users_by_email, counters):
        organizations_by_name = {}

        for organization_data in ORGANIZATIONS:
            owner = users_by_email[organization_data["owner_email"]]
            organization_defaults = {
                "name": organization_data["name"],
                "legal_name": organization_data["legal_name"],
                "tax_id": organization_data["tax_id"],
                "billing_email": organization_data["billing_email"],
                "billing_address": organization_data["billing_address"],
                "billing_city": organization_data["billing_city"],
                "billing_country": organization_data["billing_country"],
                "billing_postal_code": organization_data["billing_postal_code"],
                "status": Organization.Status.ACTIVE,
            }
            organization, created = Organization.objects.update_or_create(
                user=owner,
                defaults=organization_defaults,
            )
            organizations_by_name[organization.name] = organization
            if created:
                counters["organizations"] += 1

            for service_data in organization_data["services"]:
                service, service_created = Service.objects.update_or_create(
                    organization=organization,
                    name=service_data["name"],
                    defaults={"description": service_data["description"]},
                )
                if service_created:
                    counters["services"] += 1

                for subservice_data in service_data["subservices"]:
                    subservice, subservice_created = Subservice.objects.update_or_create(
                        service=service,
                        name=subservice_data["name"],
                        defaults={"description": subservice_data["description"]},
                    )
                    if subservice_created:
                        counters["subservices"] += 1

                    _, price_created = ServicePrice.objects.update_or_create(
                        subservice=subservice,
                        currency="EUR",
                        effective_from=DEFAULT_PRICE_DATE,
                        defaults={
                            "amount": subservice_data["amount"],
                            "effective_to": None,
                        },
                    )
                    if price_created:
                        counters["prices"] += 1

        return organizations_by_name

    def _seed_jobs(self, users_by_email, organizations_by_name, counters):
        for job_data in JOBS:
            user = users_by_email[job_data["user_email"]]
            organization = organizations_by_name[job_data["organization_name"]]
            service = organization.services.get(name=job_data["service_name"])
            subservice = service.subservices.get(name=job_data["subservice_name"])
            plan_price = subservice.price_table.get(
                currency="EUR",
                effective_from=DEFAULT_PRICE_DATE,
            )
            _, created = Job.objects.update_or_create(
                user=user,
                organization=organization,
                plan_price=plan_price,
                defaults={"status": job_data["status"]},
            )
            if created:
                counters["jobs"] += 1
