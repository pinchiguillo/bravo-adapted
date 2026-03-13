from django.urls import path

from .consumers import JobChatConsumer

websocket_urlpatterns = [
    path("ws/chats/<uuid:chat_uuid>/", JobChatConsumer.as_asgi()),
]

