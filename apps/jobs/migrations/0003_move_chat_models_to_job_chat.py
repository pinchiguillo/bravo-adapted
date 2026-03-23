from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("job_chat", "0001_initial"),
        ("jobs", "0002_jobchat_uuid"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="JobChatAttachment"),
                migrations.DeleteModel(name="JobChatMessage"),
                migrations.DeleteModel(name="JobChat"),
            ],
            database_operations=[],
        ),
    ]
