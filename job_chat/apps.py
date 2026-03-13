from django.apps import AppConfig


class JobChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "job_chat"

    def ready(self):
        from . import signals  # noqa: F401

