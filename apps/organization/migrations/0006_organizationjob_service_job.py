import uuid

import django.db.models.deletion
from django.db import migrations, models


def create_default_jobs_for_services(apps, schema_editor):
    OrganizationJob = apps.get_model("organization", "OrganizationJob")
    Service = apps.get_model("organization", "Service")

    default_jobs_by_organization_id = {}

    for service in Service.objects.select_related("organization").all():
        organization_id = service.organization_id
        organization_job = default_jobs_by_organization_id.get(organization_id)
        if organization_job is None:
            organization_job, _ = OrganizationJob.objects.get_or_create(
                organization_id=organization_id,
                name="General",
                defaults={"description": "Migrated default job for existing services."},
            )
            default_jobs_by_organization_id[organization_id] = organization_job

        service.job_id = organization_job.id
        service.save(update_fields=["job"])


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0005_category_description_service_category_and_service_price_charging_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_jobs",
                        to="organization.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["organization_id", "name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "name"),
                        name="unique_organization_job_name",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="service",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="services",
                to="organization.organizationjob",
            ),
        ),
        migrations.RunPython(create_default_jobs_for_services, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="service",
            name="unique_organization_service_name",
        ),
        migrations.RemoveField(
            model_name="service",
            name="organization",
        ),
        migrations.AlterField(
            model_name="service",
            name="job",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="services",
                to="organization.organizationjob",
            ),
        ),
        migrations.AlterModelOptions(
            name="service",
            options={"ordering": ["job_id", "name"]},
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(
                fields=("job", "name"),
                name="unique_job_service_name",
            ),
        ),
    ]
