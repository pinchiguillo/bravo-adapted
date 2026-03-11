"""
ASGI config for Core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from jobs.routing import websocket_urlpatterns as jobs_websocket_urlpatterns
from jobs.ws_auth import JWTAuthMiddlewareStack
from organization.routing import websocket_urlpatterns as organization_websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Core.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(
                URLRouter([*jobs_websocket_urlpatterns, *organization_websocket_urlpatterns])
            )
        ),
    }
)
