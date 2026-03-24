"""
ASGI config for Core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Core.settings')

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.apps import apps
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()


def build_websocket_application():
    from apps.organization.routing import websocket_urlpatterns as organization_websocket_urlpatterns
    websocket_router = URLRouter(organization_websocket_urlpatterns)

    if apps.is_installed("apps.jobs"):
        from apps.job_chat.ws_auth import JWTAuthMiddlewareStack

        websocket_router = JWTAuthMiddlewareStack(websocket_router)

    return AllowedHostsOriginValidator(websocket_router)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": build_websocket_application(),
    }
)
