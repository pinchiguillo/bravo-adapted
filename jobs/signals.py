from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Job, JobChat


@receiver(post_save, sender=Job)
def create_job_chat(sender, instance, created, **kwargs):
    if created:
        JobChat.objects.get_or_create(job=instance)
