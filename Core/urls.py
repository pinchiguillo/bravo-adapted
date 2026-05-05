"""
URL configuration for Core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common.views import api_version, healthcheck

urlpatterns = [
    path('admin/', admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
    path("api/version/", api_version, name="api-version"),
    path("api/auth/", include("apps.auth.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/management/notifications/", include("apps.notifications.management_urls")),
    path("api/", include("apps.organization.urls")),
    path("api/management/", include("apps.management.urls")),
    path("api/assets/", include("apps.assets.urls")),
    path("api/jobs/", include("apps.jobs.urls")),
    path("api/", include("apps.job_chat.urls")),
    path("api/management/statistics/", include("apps.statistics.management_urls")),
]

if not settings.HIDE_API_DOCS:
    urlpatterns.extend(
        [
            path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
            path(
                "api/docs/",
                SpectacularSwaggerView.as_view(url_name="api-schema"),
                name="api-docs",
            ),
        ]
    )

if settings.RGPD_MODULE_ENABLED:
    urlpatterns.append(path("api/rgpd/", include("apps.rgpd.urls")))
    urlpatterns.append(path("api/management/rgpd/", include("apps.rgpd.management_urls")))
