import django.db.models.deletion
from django.db import migrations, models


def assign_announcements_to_jobs(apps, schema_editor):
    Announcement = apps.get_model("organization", "Announcement")
    Job = apps.get_model("jobs", "Job")

    announcements_by_key = {}

    for job in Job.objects.select_related(
        "organization",
        "plan_price__subservice__service__category",
    ).all():
        service = job.plan_price.subservice.service
        announcement_key = (job.organization_id, service.id)
        announcement = announcements_by_key.get(announcement_key)

        if announcement is None:
            announcement = Announcement.objects.create(
                organization_id=job.organization_id,
                category_id=service.category_id,
                name=f"Migrated job {job.id}",
                location="",
                announcement="Migrated announcement",
                status="active",
                description="Auto-generated during job schema migration.",
                free_text="",
            )
            announcement.services.add(service)
            announcements_by_key[announcement_key] = announcement

        job.announcement_id = announcement.id
        job.save(update_fields=["announcement"])


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0006_organizationjob_service_job"),
        ("jobs", "0004_job_organization_rating"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="announcement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="jobs",
                to="organization.announcement",
            ),
        ),
        migrations.RunPython(assign_announcements_to_jobs, migrations.RunPython.noop),
    ]
