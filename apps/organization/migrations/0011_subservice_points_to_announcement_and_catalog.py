import django.db.models.deletion
from django.db import migrations, models


def migrate_subservices_to_announcements(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0010_announcementimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="subservice",
            name="announcement",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subservices",
                to="organization.announcement",
            ),
        ),
        migrations.AddField(
            model_name="subservice",
            name="service_catalog",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subservices",
                to="organization.servicecatalog",
            ),
        ),
        migrations.RunPython(
            migrate_subservices_to_announcements,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="announcement",
            name="services",
        ),
        migrations.RemoveConstraint(
            model_name="subservice",
            name="unique_service_subservice_name",
        ),
        migrations.RemoveField(
            model_name="subservice",
            name="service",
        ),
        migrations.DeleteModel(
            name="Service",
        ),
        migrations.AlterField(
            model_name="subservice",
            name="announcement",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subservices",
                to="organization.announcement",
            ),
        ),
        migrations.AlterField(
            model_name="subservice",
            name="service_catalog",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subservices",
                to="organization.servicecatalog",
            ),
        ),
        migrations.AlterModelOptions(
            name="subservice",
            options={"ordering": ["announcement_id", "service_catalog_id", "name"]},
        ),
        migrations.AddConstraint(
            model_name="subservice",
            constraint=models.UniqueConstraint(
                fields=("announcement", "service_catalog", "name"),
                name="unique_announcement_service_catalog_subservice_name",
            ),
        ),
    ]
