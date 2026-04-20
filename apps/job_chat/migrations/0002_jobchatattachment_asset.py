import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0001_initial"),
        ("job_chat", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="jobchatattachment",
            name="file",
        ),
        migrations.AddField(
            model_name="jobchatattachment",
            name="asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="job_chat_attachments",
                to="assets.asset",
            ),
        ),
    ]
