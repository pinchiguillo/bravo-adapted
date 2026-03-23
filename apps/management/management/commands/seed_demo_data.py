from datetime import date

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.job_chat.models import JobChat, JobChatAttachment, JobChatMessage
from apps.jobs.models import Job
from apps.organization.models import (
    Announcement,
    AnnouncementReview,
    Category,
    Organization,
    OrganizationJob,
    Service,
    ServicePrice,
    Subservice,
)

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

ANNOUNCEMENT_CATEGORIES = [
    {"name": "Reformas", "description": "Servicios vinculados a reformas y obras."},
    {"name": "Mantenimiento", "description": "Servicios recurrentes de mantenimiento."},
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
        "verification_level": 3,
        "is_approved": True,
        "services": [
            {
                "name": "Pintura",
                "category": "Reformas",
                "description": "Trabajos de pintura interior y exterior.",
                "subservices": [
                    {"name": "Piso completo", "description": "Pintura integral de vivienda.", "amount": "950.00"},
                    {"name": "Habitacion individual", "description": "Pintura de una estancia.", "amount": "180.00"},
                ],
            },
            {
                "name": "Electricidad",
                "category": "Reformas",
                "description": "Instalaciones y reparaciones electricas.",
                "subservices": [
                    {"name": "Boletin electrico", "description": "Revision y boletin.", "amount": "220.00"},
                    {"name": "Cuadro electrico", "description": "Sustitucion de cuadro.", "amount": "390.00"},
                ],
            },
        ],
        "announcements": [
            {
                "category": "Reformas",
                "service_names": ["Pintura", "Electricidad"],
                "name": "Reforma integral con visita tecnica",
                "location": "Madrid",
                "announcement": "Presupuesto en 48 horas para reformas integrales.",
                "description": "Coordinamos pintura, electricidad y acabados para viviendas.",
                "free_text": "Incluye visita tecnica inicial y plan de trabajo.",
                "latitude": "40.416775",
                "longitude": "-3.703790",
                "review_content": "Anuncio revisado y aprobado para publicacion.",
            }
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
        "verification_level": 2,
        "is_approved": False,
        "services": [
            {
                "name": "Fontaneria",
                "category": "Mantenimiento",
                "description": "Reparaciones y renovaciones de fontaneria.",
                "subservices": [
                    {"name": "Fuga urgente", "description": "Reparacion rapida de fuga.", "amount": "140.00"},
                    {"name": "Cambio de griferia", "description": "Sustitucion de grifos.", "amount": "95.00"},
                ],
            },
            {
                "name": "Limpieza",
                "category": "Mantenimiento",
                "description": "Servicios de limpieza profesional.",
                "subservices": [
                    {"name": "Fin de obra", "description": "Limpieza tras reforma.", "amount": "310.00"},
                    {"name": "Mantenimiento semanal", "description": "Servicio recurrente.", "amount": "85.00"},
                ],
            },
        ],
        "announcements": [
            {
                "category": "Mantenimiento",
                "service_names": ["Fontaneria", "Limpieza"],
                "name": "Mantenimiento de comunidades",
                "location": "Valencia",
                "announcement": "Atencion recurrente para incidencias y limpieza.",
                "description": "Cobertura mensual para portales, zonas comunes y averias.",
                "free_text": "Servicio coordinado para administradores de fincas.",
                "latitude": "39.469907",
                "longitude": "-0.376288",
                "review_content": "Texto validado para su difusion en el marketplace.",
            }
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
        "organization_rating": None,
        "messages": [
            {
                "sender_email": "ana.client@example.com",
                "content": "Necesito pintar el piso completo antes de final de mes.",
            },
            {
                "sender_email": "bruno.owner@example.com",
                "content": "Podemos hacer visita tecnica esta semana.",
                "attachment_name": "visita-tecnica.txt",
                "attachment_content": "Disponibilidad para visita tecnica: martes y jueves por la tarde.",
            },
        ],
    },
    {
        "user_email": "ana.client@example.com",
        "organization_name": "Bravo Reformas",
        "service_name": "Electricidad",
        "subservice_name": "Cuadro electrico",
        "status": Job.Status.ACTIVE,
        "organization_rating": None,
        "messages": [
            {
                "sender_email": "ana.client@example.com",
                "content": "El cuadro electrico necesita sustitucion urgente.",
            },
            {
                "sender_email": "bruno.owner@example.com",
                "content": "Te envio el alcance preliminar y materiales.",
            },
        ],
    },
    {
        "user_email": "ana.client@example.com",
        "organization_name": "Casa Lista",
        "service_name": "Fontaneria",
        "subservice_name": "Fuga urgente",
        "status": Job.Status.COMPLETED,
        "organization_rating": "4.50",
        "messages": [
            {
                "sender_email": "ana.client@example.com",
                "content": "La fuga del bano ya esta resuelta, gracias.",
            }
        ],
    },
    {
        "user_email": "ana.client@example.com",
        "organization_name": "Casa Lista",
        "service_name": "Limpieza",
        "subservice_name": "Fin de obra",
        "status": Job.Status.REJECTED,
        "organization_rating": None,
        "messages": [
            {
                "sender_email": "carla.owner@example.com",
                "content": "No tenemos disponibilidad para esa fecha concreta.",
            }
        ],
    },
]

RGPD_USER_CONSENTS = [
    {
        "user_email": "ana.client@example.com",
        "cookies_accepted": True,
        "cookies_version": "2026-03",
        "privacy_policy_accepted": True,
        "privacy_policy_version": "v3",
        "terms_and_conditions_accepted": True,
        "terms_and_conditions_version": "v7",
        "source": "seed-demo",
        "ip_address": "203.0.113.10",
        "user_agent": "SeedDemoData/1.0",
        "event_action": "upsert",
    },
    {
        "user_email": "bruno.owner@example.com",
        "cookies_accepted": True,
        "cookies_version": "2026-03",
        "privacy_policy_accepted": True,
        "privacy_policy_version": "v3",
        "terms_and_conditions_accepted": True,
        "terms_and_conditions_version": "v7",
        "source": "seed-demo",
        "ip_address": "203.0.113.11",
        "user_agent": "SeedDemoData/1.0",
        "event_action": "upsert",
    },
]

RGPD_ANONYMOUS_CONSENTS = [
    {
        "identifier": "seed-anon-cookie-banner",
        "write_token_hash": "seed-token-hash-cookie-banner",
        "cookies_accepted": True,
        "cookies_version": "2026-03",
        "privacy_policy_accepted": True,
        "privacy_policy_version": "v3",
        "terms_and_conditions_accepted": False,
        "terms_and_conditions_version": "",
        "source": "cookie-banner",
        "ip_address": "198.51.100.20",
        "user_agent": "BravoLanding/1.0",
        "event_action": "create",
    },
    {
        "identifier": "seed-anon-checkout",
        "write_token_hash": "seed-token-hash-checkout",
        "cookies_accepted": True,
        "cookies_version": "2026-03",
        "privacy_policy_accepted": True,
        "privacy_policy_version": "v3",
        "terms_and_conditions_accepted": True,
        "terms_and_conditions_version": "v7",
        "source": "checkout",
        "ip_address": "198.51.100.21",
        "user_agent": "BravoCheckout/2.0",
        "event_action": "upsert",
    },
]


class Command(BaseCommand):
    help = "Seeds demo data for all concrete domain models."

    @transaction.atomic
    def handle(self, *args, **options):
        counters = {
            "users": 0,
            "organizations": 0,
            "services": 0,
            "subservices": 0,
            "prices": 0,
            "categories": 0,
            "announcements": 0,
            "announcement_reviews": 0,
            "jobs": 0,
            "job_chats": 0,
            "job_chat_messages": 0,
            "job_chat_attachments": 0,
            "rgpd_consents": 0,
            "rgpd_consent_events": 0,
            "rgpd_anonymous_consents": 0,
            "rgpd_anonymous_consent_events": 0,
        }
        users_by_email = self._seed_users(counters)
        categories_by_name = self._seed_categories(counters)
        organizations_by_name = self._seed_organizations(users_by_email, categories_by_name, counters)
        self._seed_jobs(users_by_email, organizations_by_name, counters)
        if settings.RGPD_MODULE_ENABLED:
            self._seed_rgpd(users_by_email, counters)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed completed "
                f"(created={sum(counters.values())}, "
                f"users={counters['users']}, "
                f"organizations={counters['organizations']}, "
                f"services={counters['services']}, "
                f"subservices={counters['subservices']}, "
                f"prices={counters['prices']}, "
                f"categories={counters['categories']}, "
                f"announcements={counters['announcements']}, "
                f"announcement_reviews={counters['announcement_reviews']}, "
                f"jobs={counters['jobs']}, "
                f"job_chats={counters['job_chats']}, "
                f"job_chat_messages={counters['job_chat_messages']}, "
                f"job_chat_attachments={counters['job_chat_attachments']}, "
                f"rgpd_consents={counters['rgpd_consents']}, "
                f"rgpd_consent_events={counters['rgpd_consent_events']}, "
                f"rgpd_anonymous_consents={counters['rgpd_anonymous_consents']}, "
                f"rgpd_anonymous_consent_events={counters['rgpd_anonymous_consent_events']}). "
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

    def _seed_categories(self, counters):
        categories_by_name = {}

        for category_data in ANNOUNCEMENT_CATEGORIES:
            category, created = Category.objects.get_or_create(
                name=category_data["name"],
                defaults={"description": category_data["description"]},
            )
            if not created and category.description != category_data["description"]:
                category.description = category_data["description"]
                category.save(update_fields=["description"])
            categories_by_name[category_data["name"]] = category
            if created:
                counters["categories"] += 1

        return categories_by_name

    def _seed_organizations(self, users_by_email, categories_by_name, counters):
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
                "verification_level": organization_data["verification_level"],
                "is_approved": organization_data["is_approved"],
                "status": Organization.Status.ACTIVE,
            }
            organization, created = Organization.objects.update_or_create(
                user=owner,
                defaults=organization_defaults,
            )
            organizations_by_name[organization.name] = organization
            if created:
                counters["organizations"] += 1
            organization_job, organization_job_created = OrganizationJob.objects.update_or_create(
                organization=organization,
                name=f"{organization.name} services",
                defaults={"description": f"Default organization job for {organization.name}."},
            )
            if organization_job_created:
                counters.setdefault("organization_jobs", 0)
                counters["organization_jobs"] += 1

            for service_data in organization_data["services"]:
                service_category = categories_by_name[service_data["category"]]
                service, service_created = Service.objects.update_or_create(
                    job=organization_job,
                    name=service_data["name"],
                    defaults={
                        "category": service_category,
                        "description": service_data["description"],
                    },
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
                            "charging_type": ServicePrice.ChargingType.PER_PROJECT,
                            "effective_to": None,
                        },
                    )
                    if price_created:
                        counters["prices"] += 1

            for announcement_data in organization_data.get("announcements", []):
                category = categories_by_name[announcement_data["category"]]
                announcement, announcement_created = Announcement.objects.update_or_create(
                    organization=organization,
                    name=announcement_data["name"],
                    defaults={
                        "category": category,
                        "location": announcement_data["location"],
                        "announcement": announcement_data["announcement"],
                        "status": Announcement.Status.ACTIVE,
                        "description": announcement_data["description"],
                        "free_text": announcement_data["free_text"],
                        "latitude": announcement_data["latitude"],
                        "longitude": announcement_data["longitude"],
                    },
                )
                announcement.services.set(
                    organization_job.services.filter(name__in=announcement_data["service_names"])
                )
                if announcement_created:
                    counters["announcements"] += 1

                _, review_created = AnnouncementReview.objects.update_or_create(
                    announcement=announcement,
                    defaults={"content": announcement_data["review_content"]},
                )
                if review_created:
                    counters["announcement_reviews"] += 1

        return organizations_by_name

    def _seed_jobs(self, users_by_email, organizations_by_name, counters):
        for job_data in JOBS:
            user = users_by_email[job_data["user_email"]]
            organization = organizations_by_name[job_data["organization_name"]]
            service = Service.objects.select_related("job", "job__organization").get(
                job__organization=organization,
                name=job_data["service_name"],
            )
            announcement = organization.announcements.filter(services=service).order_by("id").first()
            if announcement is None:
                announcement = Announcement.objects.create(
                    organization=organization,
                    category=service.category,
                    name=f"{service.name} autogenerated announcement",
                    location=organization.billing_city,
                    announcement=f"Generated announcement for {service.name}.",
                    status=Announcement.Status.ACTIVE,
                )
                announcement.services.add(service)
            subservice = service.subservices.get(name=job_data["subservice_name"])
            plan_price = subservice.price_table.get(
                currency="EUR",
                effective_from=DEFAULT_PRICE_DATE,
            )
            _, created = Job.objects.update_or_create(
                user=user,
                announcement=announcement,
                plan_price=plan_price,
                defaults={
                    "status": job_data["status"],
                    "organization_rating": job_data["organization_rating"],
                },
            )
            job = Job.objects.get(
                user=user,
                announcement=announcement,
                plan_price=plan_price,
            )
            if created:
                counters["jobs"] += 1

            chat, chat_created = JobChat.objects.get_or_create(job=job)
            if chat_created:
                counters["job_chats"] += 1

            for index, message_data in enumerate(job_data.get("messages", []), start=1):
                sender = users_by_email[message_data["sender_email"]]
                message, message_created = JobChatMessage.objects.update_or_create(
                    chat=chat,
                    sender=sender,
                    content=message_data["content"],
                    defaults={},
                )
                if message_created:
                    counters["job_chat_messages"] += 1

                attachment_name = message_data.get("attachment_name")
                if not attachment_name:
                    continue

                attachment = message.attachments.filter(
                    uploaded_by=sender,
                    file__contains=f"/{attachment_name}",
                ).first()
                if attachment is None:
                    attachment = message.attachments.filter(uploaded_by=sender).first()
                if attachment is not None:
                    continue

                created_attachment = JobChatAttachment(
                    message=message,
                    uploaded_by=sender,
                )
                created_attachment.file.save(
                    f"seed/{job.uuid}-{index}-{attachment_name}",
                    ContentFile(message_data["attachment_content"]),
                    save=True,
                )
                counters["job_chat_attachments"] += 1

    def _seed_rgpd(self, users_by_email, counters):
        rgpd_consent_model = apps.get_model("rgpd", "RgpdConsent")
        rgpd_consent_event_model = apps.get_model("rgpd", "RgpdConsentEvent")
        rgpd_anonymous_consent_model = apps.get_model("rgpd", "RgpdAnonymousConsent")
        rgpd_anonymous_consent_event_model = apps.get_model("rgpd", "RgpdAnonymousConsentEvent")

        for consent_data in RGPD_USER_CONSENTS:
            user = users_by_email[consent_data["user_email"]]
            consent_defaults = {
                key: value
                for key, value in consent_data.items()
                if key not in {"user_email", "event_action"}
            }
            consent, consent_created = rgpd_consent_model.objects.update_or_create(
                user=user,
                defaults=consent_defaults,
            )
            if consent_created:
                counters["rgpd_consents"] += 1

            _, event_created = rgpd_consent_event_model.objects.update_or_create(
                consent=consent,
                action=consent_data["event_action"],
                defaults=consent.build_event_payload(),
            )
            if event_created:
                counters["rgpd_consent_events"] += 1

        for consent_data in RGPD_ANONYMOUS_CONSENTS:
            consent_defaults = {
                key: value
                for key, value in consent_data.items()
                if key not in {"identifier", "event_action"}
            }
            consent, consent_created = rgpd_anonymous_consent_model.objects.update_or_create(
                identifier=consent_data["identifier"],
                defaults=consent_defaults,
            )
            if consent_created:
                counters["rgpd_anonymous_consents"] += 1

            _, event_created = rgpd_anonymous_consent_event_model.objects.update_or_create(
                consent=consent,
                action=consent_data["event_action"],
                defaults=consent.build_event_payload(),
            )
            if event_created:
                counters["rgpd_anonymous_consent_events"] += 1
