from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("job_chat", "0002_jobchatattachment_asset"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobchatmessage",
            name="type",
            field=models.CharField(
                choices=[("plain_text", "Plain text"), ("widget", "Widget")],
                default="plain_text",
                max_length=20,
            ),
        ),
    ]
