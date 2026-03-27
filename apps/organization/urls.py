from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AnnouncementViewSet,
    CategoryViewSet,
    OrganizationSearchViewSet,
    OrganizationViewSet,
    PublicServicePriceViewSet,
    PublicSubserviceViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="organization-category")
router.register("", OrganizationViewSet, basename="organization")

public_subservice_list = PublicSubserviceViewSet.as_view({"get": "list"})
public_subservice_detail = PublicSubserviceViewSet.as_view({"get": "retrieve"})
public_service_price_list = PublicServicePriceViewSet.as_view({"get": "list"})
public_service_price_detail = PublicServicePriceViewSet.as_view({"get": "retrieve"})
announcement_list = AnnouncementViewSet.as_view({"get": "list", "post": "create"})
announcement_detail = AnnouncementViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)
organization_search = OrganizationSearchViewSet.as_view({"get": "list"})

urlpatterns = [
    path(
        "search/",
        organization_search,
        name="organization-search",
    ),
    path(
        "<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/",
        public_subservice_list,
        name="public-subservice-list",
    ),
    path(
        "<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/<uuid:subservice_uuid>/",
        public_subservice_detail,
        name="public-subservice-detail",
    ),
    path(
        "<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/<uuid:subservice_uuid>/prices/",
        public_service_price_list,
        name="public-service-price-list",
    ),
    path(
        "<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/<uuid:subservice_uuid>/prices/<uuid:price_uuid>/",
        public_service_price_detail,
        name="public-service-price-detail",
    ),
    path(
        "<uuid:organization_uuid>/announcements/",
        announcement_list,
        name="organization-announcement-list",
    ),
    path(
        "<uuid:organization_uuid>/announcements/<uuid:uuid>/",
        announcement_detail,
        name="organization-announcement-detail",
    ),
] + router.urls
