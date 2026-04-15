from django.core.management.base import BaseCommand
from django.db import transaction

from apps.management.models import FeatureFlag
from apps.organization.models import AllowedCity, Category, PlanTierCatalog, ServiceCatalog

CATEGORIES = [
    {"name": "Reformas", "description": "Servicios vinculados a reformas y obras."},
    {"name": "Mantenimiento", "description": "Servicios recurrentes de mantenimiento."},
]

SERVICE_CATALOGS = [
    {
        "name": "Pintura",
        "category": "Reformas",
        "description": "Trabajos de pintura interior y exterior.",
    },
    {
        "name": "Electricidad",
        "category": "Reformas",
        "description": "Instalaciones y reparaciones electricas.",
    },
    {
        "name": "Fontaneria",
        "category": "Mantenimiento",
        "description": "Reparaciones y renovaciones de fontaneria.",
    },
    {
        "name": "Limpieza",
        "category": "Mantenimiento",
        "description": "Servicios de limpieza profesional.",
    },
]

ALLOWED_CITIES = [
    "A Coruña",
    "Albacete",
    "Alicante",
    "Almería",
    "Oviedo",
    "Ávila",
    "Badajoz",
    "Barcelona",
    "Bilbao",
    "Burgos",
    "Cáceres",
    "Cádiz",
    "Castellón de la Plana",
    "Ciudad Real",
    "Córdoba",
    "Cuenca",
    "Donostia-San Sebastián",
    "Girona",
    "Granada",
    "Guadalajara",
    "Huelva",
    "Huesca",
    "Jaén",
    "León",
    "Lleida",
    "Logroño",
    "Lugo",
    "Madrid",
    "Málaga",
    "Murcia",
    "Ourense",
    "Palencia",
    "Palma",
    "Pamplona",
    "Las Palmas de Gran Canaria",
    "Pontevedra",
    "Salamanca",
    "Santa Cruz de Tenerife",
    "Santander",
    "Segovia",
    "Sevilla",
    "Soria",
    "Tarragona",
    "Teruel",
    "Toledo",
    "València",
    "Valladolid",
    "Vitoria-Gasteiz",
    "Zamora",
    "Zaragoza",
]

FEATURE_FLAGS = [
]

PLAN_TIERS = [
    {
        "key": "default",
        "name": "Default",
        "description": "Tier base para organizaciones con configuracion estandar.",
        "sort_order": 10,
    },
    {
        "key": "premium",
        "name": "Premium",
        "description": "Tier con condiciones comerciales avanzadas.",
        "sort_order": 20,
    },
    {
        "key": "pro",
        "name": "Pro",
        "description": "Tier profesional para organizaciones con mas volumen.",
        "sort_order": 30,
    },
    {
        "key": "ultra",
        "name": "Ultra",
        "description": "Tier de maximas prestaciones y personalizacion.",
        "sort_order": 40,
    },
]


class Command(BaseCommand):
    help = (
        "Seeds fixed catalog tables for categories, plan tiers and service "
        "catalogs, excluding subservices, plus feature flags."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        counters = {
            "allowed_cities_created": 0,
            "categories_created": 0,
            "categories_updated": 0,
            "allowed_cities_updated": 0,
            "service_catalogs_created": 0,
            "service_catalogs_updated": 0,
            "plan_tiers_created": 0,
            "plan_tiers_updated": 0,
            "feature_flags_created": 0,
            "feature_flags_updated": 0,
        }

        self._seed_allowed_cities(counters)
        categories_by_name = self._seed_categories(counters)
        self._seed_plan_tiers(counters)
        self._seed_service_catalogs(categories_by_name, counters)
        self._seed_feature_flags(counters)

        self.stdout.write(
            self.style.SUCCESS(
                "Fixed tables seed completed "
                f"(allowed_cities_created={counters['allowed_cities_created']}, "
                f"allowed_cities_updated={counters['allowed_cities_updated']}, "
                f"categories_created={counters['categories_created']}, "
                f"categories_updated={counters['categories_updated']}, "
                f"plan_tiers_created={counters['plan_tiers_created']}, "
                f"plan_tiers_updated={counters['plan_tiers_updated']}, "
                f"service_catalogs_created={counters['service_catalogs_created']}, "
                f"service_catalogs_updated={counters['service_catalogs_updated']}, "
                f"feature_flags_created={counters['feature_flags_created']}, "
                f"feature_flags_updated={counters['feature_flags_updated']})."
            )
        )

    def _seed_allowed_cities(self, counters):
        for city_name in ALLOWED_CITIES:
            _, created = AllowedCity.objects.get_or_create(name=city_name)

            if created:
                counters["allowed_cities_created"] += 1

    def _seed_categories(self, counters):
        categories_by_name = {}

        for category_data in CATEGORIES:
            category, created = Category.objects.get_or_create(
                name=category_data["name"],
                defaults={"description": category_data["description"]},
            )

            if created:
                counters["categories_created"] += 1
            elif category.description != category_data["description"]:
                category.description = category_data["description"]
                category.save(update_fields=["description"])
                counters["categories_updated"] += 1

            categories_by_name[category.name] = category

        return categories_by_name

    def _seed_service_catalogs(self, categories_by_name, counters):
        for catalog_data in SERVICE_CATALOGS:
            category = categories_by_name[catalog_data["category"]]
            catalog, created = ServiceCatalog.objects.get_or_create(
                name=catalog_data["name"],
                defaults={
                    "category": category,
                    "description": catalog_data["description"],
                },
            )

            if created:
                counters["service_catalogs_created"] += 1
                continue

            updated_fields = []
            if catalog.category_id != category.id:
                catalog.category = category
                updated_fields.append("category")
            if catalog.description != catalog_data["description"]:
                catalog.description = catalog_data["description"]
                updated_fields.append("description")

            if updated_fields:
                catalog.save(update_fields=updated_fields)
                counters["service_catalogs_updated"] += 1

    def _seed_plan_tiers(self, counters):
        for tier_data in PLAN_TIERS:
            tier, created = PlanTierCatalog.objects.get_or_create(
                key=tier_data["key"],
                defaults={
                    "name": tier_data["name"],
                    "description": tier_data["description"],
                    "sort_order": tier_data["sort_order"],
                },
            )

            if created:
                counters["plan_tiers_created"] += 1
                continue

            updated_fields = []
            if tier.name != tier_data["name"]:
                tier.name = tier_data["name"]
                updated_fields.append("name")
            if tier.description != tier_data["description"]:
                tier.description = tier_data["description"]
                updated_fields.append("description")
            if tier.sort_order != tier_data["sort_order"]:
                tier.sort_order = tier_data["sort_order"]
                updated_fields.append("sort_order")

            if updated_fields:
                tier.save(update_fields=updated_fields)
                counters["plan_tiers_updated"] += 1

    def _seed_feature_flags(self, counters):
        for flag_data in FEATURE_FLAGS:
            flag, created = FeatureFlag.objects.get_or_create(
                key=flag_data["key"],
                defaults={
                    "name": flag_data["name"],
                    "description": flag_data["description"],
                    "is_active": flag_data["is_active"],
                },
            )

            if created:
                counters["feature_flags_created"] += 1
                continue

            updated_fields = []
            if flag.name != flag_data["name"]:
                flag.name = flag_data["name"]
                updated_fields.append("name")
            if flag.description != flag_data["description"]:
                flag.description = flag_data["description"]
                updated_fields.append("description")
            if flag.is_active != flag_data["is_active"]:
                flag.is_active = flag_data["is_active"]
                updated_fields.append("is_active")

            if updated_fields:
                flag.save(update_fields=updated_fields)
                counters["feature_flags_updated"] += 1
