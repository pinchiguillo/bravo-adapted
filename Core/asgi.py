"""
ASGI config for Core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Core.settings')

from channels.routing import ProtocolTypeRouter, URLRouter
from django.apps import apps
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()


def build_websocket_application():
    websocket_urlpatterns = []

    if apps.is_installed("apps.jobs"):
        from apps.job_chat.routing import websocket_urlpatterns as job_chat_websocket_urlpatterns
        from apps.job_chat.ws_auth import JWTAuthMiddlewareStack

        websocket_urlpatterns.extend(job_chat_websocket_urlpatterns)
        return JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))

    return URLRouter(websocket_urlpatterns)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": build_websocket_application(),
    }
)
