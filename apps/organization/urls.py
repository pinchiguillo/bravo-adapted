from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AnnouncementViewSet,
    CategoryServiceViewSet,
    CategoryViewSet,
    OrganizationSearchViewSet,
    OrganizationViewSet,
    PublicAnnouncementDetailViewSet,
    PublicAnnouncementViewSet,
    PublicServicePriceViewSet,
    PublicSubserviceViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="organization-category")
router.register("organizations", OrganizationViewSet, basename="organization")

public_subservice_list = PublicSubserviceViewSet.as_view({"get": "list"})
public_subservice_detail = PublicSubserviceViewSet.as_view({"get": "retrieve"})
public_service_price_list = PublicServicePriceViewSet.as_view({"get": "list"})
public_service_price_detail = PublicServicePriceViewSet.as_view({"get": "retrieve"})
category_service_list = CategoryServiceViewSet.as_view({"get": "list"})
public_announcement_list = PublicAnnouncementViewSet.as_view({"get": "list"})
public_announcement_detail = PublicAnnouncementDetailViewSet.as_view({"get": "retrieve"})
announcement_list = AnnouncementViewSet.as_view({"get": "list", "post": "create"})
announcement_detail = AnnouncementViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)
organization_search = OrganizationSearchViewSet.as_view({"get": "list"})

urlpatterns = [
    path(
        "<uuid:category_uuid>/services/",
        category_service_list,
        name="category-service-list",
    ),
    path(
        "announcements/",
        public_announcement_list,
        name="public-announcement-list",
    ),
    path(
        "announcements/<uuid:organization_uuid>/<uuid:uuid>/",
        public_announcement_detail,
        name="public-announcement-detail",
    ),
    path(
        "organizations/search/",
        organization_search,
        name="organization-search",
    ),
    path(
        "organizations/<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/",
        public_subservice_list,
        name="public-subservice-list",
    ),
    path(
        "organizations/<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/<uuid:subservice_uuid>/",
        public_subservice_detail,
        name="public-subservice-detail",
    ),
    path(
        "organizations/<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/<uuid:subservice_uuid>/prices/",
        public_service_price_list,
        name="public-service-price-list",
    ),
    path(
        "organizations/<uuid:organization_uuid>/services/<uuid:service_uuid>/subservices/<uuid:subservice_uuid>/prices/<uuid:price_uuid>/",
        public_service_price_detail,
        name="public-service-price-detail",
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
] + router.urls
