from django.urls import path

from .views import JobChatConsumer

websocket_urlpatterns = [
    path("ws/jobs/<uuid:job_uuid>/chat/", JobChatConsumer.as_asgi()),
]
