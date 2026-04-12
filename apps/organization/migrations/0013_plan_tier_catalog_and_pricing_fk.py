import uuid

from django.db import migrations, models
import django.db.models.deletion


def seed_plan_tiers(apps, schema_editor):
    PlanTierCatalog = apps.get_model("organization", "PlanTierCatalog")

    tiers = [
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

    for tier in tiers:
        PlanTierCatalog.objects.update_or_create(
            key=tier["key"],
            defaults={
                "name": tier["name"],
                "description": tier["description"],
                "sort_order": tier["sort_order"],
            },
        )


def assign_plan_tiers(apps, schema_editor):
    OrganizationPricing = apps.get_model("organization", "OrganizationPricing")
    PlanTierCatalog = apps.get_model("organization", "PlanTierCatalog")

    plan_mapping = {
        "starter": "default",
        "growth": "premium",
        "scale": "pro",
        "enterprise": "ultra",
    }
    tiers_by_key = {
        tier.key: tier.id
        for tier in PlanTierCatalog.objects.filter(key__in=plan_mapping.values())
    }
    default_tier_id = tiers_by_key["default"]

    for pricing in OrganizationPricing.objects.all().only("id", "plan_type"):
        pricing.plan_tier_id = tiers_by_key.get(plan_mapping.get(pricing.plan_type, "default"), default_tier_id)
        pricing.save(update_fields=["plan_tier"])


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0012_organizationpricing"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanTierCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("key", models.SlugField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.RunPython(seed_plan_tiers, migrations.RunPython.noop),
        migrations.AddField(
            model_name="organizationpricing",
            name="plan_tier",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="organization_pricings",
                to="organization.plantiercatalog",
            ),
        ),
        migrations.RunPython(assign_plan_tiers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="organizationpricing",
            name="plan_tier",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="organization_pricings",
                to="organization.plantiercatalog",
            ),
        ),
        migrations.RemoveField(
            model_name="organizationpricing",
            name="plan_type",
        ),
    ]
