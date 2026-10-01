from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.jobs.views import create_announcement_job

from .views import (
    AllowedCityViewSet,
    AnnouncementImageViewSet,
    AnnouncementViewSet,
    CategoryViewSet,
    OrganizationAnnouncementImageBase64ViewSet,
    OrganizationViewSet,
    PlanTierCatalogViewSet,
    PublicAnnouncementDetailViewSet,
    PublicAnnouncementImageBase64ViewSet,
    PublicAnnouncementViewSet,
    ServiceCatalogViewSet,
    ServicePriceViewSet,
    SubserviceViewSet,
    announcement_favorite,
    list_my_favorites,
)

router = DefaultRouter()
router.register("allowed-cities", AllowedCityViewSet, basename="organization-allowed-city")
router.register("categories", CategoryViewSet, basename="organization-category")
router.register("plan-tiers", PlanTierCatalogViewSet, basename="organization-plan-tier")
router.register("services", ServiceCatalogViewSet, basename="service-catalog")
router.register("organizations", OrganizationViewSet, basename="organization")

public_announcement_list = PublicAnnouncementViewSet.as_view({"get": "list"})
public_announcement_detail = PublicAnnouncementDetailViewSet.as_view({"get": "retrieve"})
announcement_list = AnnouncementViewSet.as_view({"get": "list", "post": "create"})
announcement_detail = AnnouncementViewSet.as_view({"put": "update", "patch": "partial_update", "delete": "destroy"})
announcement_image_list = AnnouncementImageViewSet.as_view({"get": "list", "post": "create"})
announcement_image_complete = AnnouncementImageViewSet.as_view({"post": "complete_upload"})
announcement_image_detail = AnnouncementImageViewSet.as_view({"delete": "destroy"})
announcement_image_base64 = OrganizationAnnouncementImageBase64ViewSet.as_view({"get": "retrieve"})
public_announcement_image_base64 = PublicAnnouncementImageBase64ViewSet.as_view({"get": "retrieve"})
subservice_list = SubserviceViewSet.as_view({"get": "list", "post": "create"})
subservice_detail = SubserviceViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)
service_price_list = ServicePriceViewSet.as_view({"get": "list", "post": "create"})
service_price_detail = ServicePriceViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    path(
        "announcements/favorites/",
        list_my_favorites,
        name="announcement-favorites-list",
    ),
    path(
        "announcements/<uuid:uuid>/favorite/",
        announcement_favorite,
        name="announcement-favorite",
    ),
    path(
        "announcements/<uuid:announcement_uuid>/subservices/",
        subservice_list,
        name="organization-subservice-list",
    ),
    path(
        ("announcements/<uuid:announcement_uuid>/subservices/<uuid:subservice_uuid>/"),
        subservice_detail,
        name="organization-subservice-detail",
    ),
    path(
        ("announcements/<uuid:announcement_uuid>/subservices/<uuid:subservice_uuid>/prices/"),
        service_price_list,
        name="organization-service-price-list",
    ),
    path(
        ("announcements/<uuid:announcement_uuid>/subservices/<uuid:subservice_uuid>/prices/<uuid:price_uuid>/"),
        service_price_detail,
        name="organization-service-price-detail",
    ),
    path(
        "announcements/",
        public_announcement_list,
        name="public-announcement-list",
    ),
    path(
        "announcements/<uuid:uuid>/",
        public_announcement_detail,
        name="public-announcement-detail",
    ),
    path(
        "announcements/<uuid:announcement_uuid>/jobs/",
        create_announcement_job,
        name="announcement-job-create",
    ),
    path(
        "announcements/<uuid:uuid>/images/<uuid:image_uuid>/base64/",
        public_announcement_image_base64,
        name="public-announcement-image-base64",
    ),
    path(
        "organizations/<uuid:organization_uuid>/announcements/",
        announcement_list,
        name="organization-announcement-list",
    ),
    path(
        "organizations/<uuid:organization_uuid>/announcements/<uuid:uuid>/",
        announcement_detail,
        name="organization-announcement-detail",
    ),
    path(
        "organizations/<uuid:organization_uuid>/announcements/<uuid:uuid>/images/",
        announcement_image_list,
        name="organization-announcement-image-list",
    ),
    path(
        "organizations/<uuid:organization_uuid>/announcements/<uuid:uuid>/images/complete/",
        announcement_image_complete,
        name="organization-announcement-image-complete",
    ),
    path(
        "organizations/<uuid:organization_uuid>/announcements/<uuid:uuid>/images/<uuid:image_uuid>/",
        announcement_image_detail,
        name="organization-announcement-image-detail",
    ),
    path(
        "organizations/<uuid:organization_uuid>/announcements/<uuid:uuid>/images/<uuid:image_uuid>/base64/",
        announcement_image_base64,
        name="organization-announcement-image-base64",
    ),
    *router.urls,
]
