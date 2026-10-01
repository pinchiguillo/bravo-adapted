from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ManagementAllowedCityViewSet,
    ManagementAnnouncementStatusChangeViewSet,
    ManagementAnnouncementViewSet,
    ManagementAssetStatsView,
    ManagementAssetViewSet,
    ManagementCategoryViewSet,
    ManagementChatViewSet,
    ManagementFeatureFlagViewSet,
    ManagementJobViewSet,
    ManagementOrganizationViewSet,
    ManagementPlanTierCatalogViewSet,
    ManagementServiceCatalogViewSet,
    ManagementStatsView,
    ManagementUserViewSet,
)

router = DefaultRouter()
# No browsable index of the staff API.
router.include_root_view = False
router.register("users", ManagementUserViewSet, basename="management-users")
router.register("feature-flags", ManagementFeatureFlagViewSet, basename="management-feature-flags")
router.register("categories", ManagementCategoryViewSet, basename="management-categories")
router.register("plan-tiers", ManagementPlanTierCatalogViewSet, basename="management-plan-tiers")
router.register("services", ManagementServiceCatalogViewSet, basename="management-services")
router.register("allowed-cities", ManagementAllowedCityViewSet, basename="management-allowed-cities")
router.register("announcements", ManagementAnnouncementViewSet, basename="management-announcements")
router.register("jobs", ManagementJobViewSet, basename="management-jobs")
router.register("chats", ManagementChatViewSet, basename="management-chats")
router.register(
    "announcement-status-changes",
    ManagementAnnouncementStatusChangeViewSet,
    basename="management-announcement-status-changes",
)
router.register("organizations", ManagementOrganizationViewSet, basename="management-organizations")
router.register("assets", ManagementAssetViewSet, basename="management-assets")

urlpatterns = [
    path("assets/stats/", ManagementAssetStatsView.as_view(), name="management-assets-stats"),
    *router.urls,
    path("stats/", ManagementStatsView.as_view(), name="management-stats"),
]
