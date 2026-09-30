from django.contrib import admin

from .models import JobChat, JobChatAttachment, JobChatMessage


@admin.register(JobChat)
class JobChatAdmin(admin.ModelAdmin):
    list_display = ("uuid", "job", "created_at")
    search_fields = ("uuid", "job__uuid")
    raw_id_fields = ("job",)


@admin.register(JobChatMessage)
class JobChatMessageAdmin(admin.ModelAdmin):
    list_display = ("uuid", "job_chat", "user", "type", "created_at")
    list_filter = ("type",)
    search_fields = ("uuid", "user__email")
    raw_id_fields = ("job_chat", "user")


@admin.register(JobChatAttachment)
class JobChatAttachmentAdmin(admin.ModelAdmin):
    list_display = ("uuid", "message", "asset", "created_at")
    raw_id_fields = ("message", "asset")
