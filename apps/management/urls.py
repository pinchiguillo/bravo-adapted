from rest_framework.routers import DefaultRouter

from .views import (
    ManagementAllowedCityViewSet,
    ManagementAnnouncementStatusChangeViewSet,
    ManagementAnnouncementViewSet,
    ManagementCategoryViewSet,
    ManagementFeatureFlagViewSet,
    ManagementOrganizationViewSet,
    ManagementPlanTierCatalogViewSet,
    ManagementServiceCatalogViewSet,
    ManagementUserViewSet,
)

router = DefaultRouter()
router.register("users", ManagementUserViewSet, basename="management-users")
router.register("feature-flags", ManagementFeatureFlagViewSet, basename="management-feature-flags")
router.register("categories", ManagementCategoryViewSet, basename="management-categories")
router.register("plan-tiers", ManagementPlanTierCatalogViewSet, basename="management-plan-tiers")
router.register("services", ManagementServiceCatalogViewSet, basename="management-services")
router.register("allowed-cities", ManagementAllowedCityViewSet, basename="management-allowed-cities")
router.register("announcements", ManagementAnnouncementViewSet, basename="management-announcements")
router.register(
    "announcement-status-changes",
    ManagementAnnouncementStatusChangeViewSet,
    basename="management-announcement-status-changes",
)
router.register("organizations", ManagementOrganizationViewSet, basename="management-organizations")

urlpatterns = router.urls
