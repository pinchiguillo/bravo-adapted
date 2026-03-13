from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    OrganizationSearchViewSet,
    OrganizationUserViewSet,
    OrganizationViewSet,
    ServiceViewSet,
    SubserviceViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="organization-category")
router.register("", OrganizationViewSet, basename="organization")

organization_user = OrganizationUserViewSet.as_view(
    {"get": "list", "post": "create", "patch": "partial_update"}
)
service_list = ServiceViewSet.as_view({"get": "list", "post": "create"})
service_detail = ServiceViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)
subservice_list = SubserviceViewSet.as_view({"get": "list", "post": "create"})
subservice_detail = SubserviceViewSet.as_view(
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
        "user/",
        organization_user,
        name="organization-user",
    ),
    path(
        "<uuid:organization_uuid>/services/",
        service_list,
        name="organization-service-list",
    ),
    path(
        "<uuid:organization_uuid>/<uuid:service_uuid>/",
        service_detail,
        name="organization-service-detail",
    ),
    path(
        "<uuid:organization_uuid>/<uuid:service_uuid>/subservices/",
        subservice_list,
        name="organization-subservice-list",
    ),
    path(
        "<uuid:organization_uuid>/<uuid:service_uuid>/<uuid:uuid>/",
        subservice_detail,
        name="organization-subservice-detail",
    ),
] + router.urls
