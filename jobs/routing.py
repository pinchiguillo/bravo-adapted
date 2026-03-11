from django.urls import path

from .consumers import JobChatConsumer

websocket_urlpatterns = [
    path("ws/jobs/<uuid:job_uuid>/chat/", JobChatConsumer.as_asgi()),
]
