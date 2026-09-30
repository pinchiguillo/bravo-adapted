"""Root URL configuration: the API is versioned by app under /api/."""
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
    path("api/rgpd/", include("apps.rgpd.urls")),
    path("api/management/rgpd/", include("apps.rgpd.management_urls")),
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
