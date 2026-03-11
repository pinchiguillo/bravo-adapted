from django.urls import path

from .consumers import OrganizationSearchConsumer

websocket_urlpatterns = [
    path("ws/organization/search/", OrganizationSearchConsumer.as_asgi()),
]
