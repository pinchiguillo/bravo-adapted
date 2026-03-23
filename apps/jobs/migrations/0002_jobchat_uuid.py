import uuid

from django.db import migrations, models


def populate_jobchat_uuid(apps, schema_editor):
    JobChat = apps.get_model("jobs", "JobChat")
    for chat in JobChat.objects.filter(uuid__isnull=True).iterator():
        chat.uuid = uuid.uuid4()
        chat.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobchat",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(populate_jobchat_uuid, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="jobchat",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
