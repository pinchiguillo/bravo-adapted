import django.db.models.deletion
import uuid
from django.db import migrations, models


def populate_service_catalog_and_organization(apps, schema_editor):
    OrganizationJob = apps.get_model("organization", "OrganizationJob")
    Service = apps.get_model("organization", "Service")
    ServiceCatalog = apps.get_model("organization", "ServiceCatalog")

    jobs_by_id = {
        job.id: job.organization_id
        for job in OrganizationJob.objects.select_related("organization").all()
    }
    catalog_ids_by_name = {}

    for service in Service.objects.all().iterator():
        catalog_id = catalog_ids_by_name.get(service.name)
        if catalog_id is None:
            catalog, _ = ServiceCatalog.objects.get_or_create(
                name=service.name,
                defaults={
                    "category_id": service.category_id,
                    "description": service.description,
                },
            )
            catalog_id = catalog.id
            catalog_ids_by_name[service.name] = catalog_id

        service.organization_id = jobs_by_id.get(service.job_id)
        service.service_catalog_id = catalog_id
        service.save(update_fields=["organization", "service_catalog"])


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0007_organization_is_approved"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="service_catalogs",
                        to="organization.category",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="service",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="services",
                to="organization.organization",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="service_catalog",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="services",
                to="organization.servicecatalog",
            ),
        ),
        migrations.RunPython(
            populate_service_catalog_and_organization,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="service",
            name="unique_job_service_name",
        ),
        migrations.RemoveField(
            model_name="service",
            name="job",
        ),
        migrations.DeleteModel(
            name="OrganizationJob",
        ),
        migrations.AlterField(
            model_name="service",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="services",
                to="organization.organization",
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="service_catalog",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="services",
                to="organization.servicecatalog",
            ),
        ),
        migrations.AlterModelOptions(
            name="service",
            options={"ordering": ["organization_id", "name"]},
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(
                fields=("organization", "service_catalog"),
                name="unique_organization_service_catalog",
            ),
        ),
    ]
