from django.apps import apps
from rest_framework.routers import DefaultRouter

from .views import (
    ManagementFeatureFlagViewSet,
    ManagementOrganizationViewSet,
    ManagementUserViewSet,
)

router = DefaultRouter()
router.register("users", ManagementUserViewSet, basename="management-users")
router.register("feature-flags", ManagementFeatureFlagViewSet, basename="management-feature-flags")
router.register("organizations", ManagementOrganizationViewSet, basename="management-organizations")

if apps.is_installed("apps.jobs"):
    from .views import ManagementJobViewSet

    router.register("jobs", ManagementJobViewSet, basename="management-jobs")

urlpatterns = router.urls
