import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0005_job_announcement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="job",
            name="announcement",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="jobs",
                to="organization.announcement",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE jobs_job DROP COLUMN IF EXISTS organization_id CASCADE;",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="job",
                    name="organization",
                ),
            ],
        ),
    ]
