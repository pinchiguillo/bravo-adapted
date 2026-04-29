from django.urls import path

from .views import get_job_chat_messages, send_job_chat_message, update_proposal_status
from .views.attachments import attach_to_message

urlpatterns = [
    path("jobs/<uuid:job_uuid>/messages/", get_job_chat_messages, name="job-chat-messages"),
    path("jobs/<uuid:job_uuid>/send/", send_job_chat_message, name="job-chat-send"),
    path(
        "jobs/<uuid:job_uuid>/messages/<uuid:message_uuid>/attachments/",
        attach_to_message,
        name="job-chat-attach",
    ),
    path(
        "jobs/<uuid:job_uuid>/messages/<uuid:message_uuid>/proposal-status/",
        update_proposal_status,
        name="update-proposal-status",
    ),
]
