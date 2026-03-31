from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AllowedCityViewSet,
    AnnouncementImageViewSet,
    AnnouncementViewSet,
    CategoryViewSet,
    OrganizationViewSet,
    PublicAnnouncementDetailViewSet,
    PublicAnnouncementViewSet,
    ServicePriceViewSet,
    ServiceCatalogViewSet,
    SubserviceViewSet,
)

router = DefaultRouter()
router.register("allowed-cities", AllowedCityViewSet, basename="organization-allowed-city")
router.register("categories", CategoryViewSet, basename="organization-category")
router.register("services", ServiceCatalogViewSet, basename="service-catalog")
router.register("organizations", OrganizationViewSet, basename="organization")

public_announcement_list = PublicAnnouncementViewSet.as_view({"get": "list"})
public_announcement_detail = PublicAnnouncementDetailViewSet.as_view({"get": "retrieve"})
announcement_list = AnnouncementViewSet.as_view({"get": "list", "post": "create"})
announcement_detail = AnnouncementViewSet.as_view(
    {"put": "update", "patch": "partial_update", "delete": "destroy"}
)
announcement_image_list = AnnouncementImageViewSet.as_view({"get": "list", "post": "create"})
announcement_image_detail = AnnouncementImageViewSet.as_view({"delete": "destroy"})
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
        "announcements/<uuid:announcement_uuid>/subservices/",
        subservice_list,
        name="organization-subservice-list",
    ),
    path(
        (
            "announcements/<uuid:announcement_uuid>/subservices/<uuid:subservice_uuid>/"
        ),
        subservice_detail,
        name="organization-subservice-detail",
    ),
    path(
        (
            "announcements/<uuid:announcement_uuid>/subservices/<uuid:subservice_uuid>/prices/"
        ),
        service_price_list,
        name="organization-service-price-list",
    ),
    path(
        (
            "announcements/<uuid:announcement_uuid>/subservices/<uuid:subservice_uuid>/prices/<uuid:price_uuid>/"
        ),
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
        "organizations/<uuid:organization_uuid>/announcements/<uuid:uuid>/images/<uuid:image_uuid>/",
        announcement_image_detail,
        name="organization-announcement-image-detail",
    ),
] + router.urls
