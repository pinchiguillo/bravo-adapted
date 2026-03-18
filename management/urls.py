from rest_framework.routers import DefaultRouter

from .views import (
    ManagementFeatureFlagViewSet,
    ManagementJobViewSet,
    ManagementOrganizationViewSet,
    ManagementUserViewSet,
)

router = DefaultRouter()
router.register("users", ManagementUserViewSet, basename="management-users")
router.register("feature-flags", ManagementFeatureFlagViewSet, basename="management-feature-flags")
router.register("organizations", ManagementOrganizationViewSet, basename="management-organizations")
router.register("jobs", ManagementJobViewSet, basename="management-jobs")

urlpatterns = router.urls
