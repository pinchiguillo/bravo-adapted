from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    OrganizationViewSet,
    ServicePriceViewSet,
    ServiceViewSet,
    SubserviceViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="organization-category")
router.register("service-prices", ServicePriceViewSet, basename="organization-service-price")
router.register("", OrganizationViewSet, basename="organization")

service_list = ServiceViewSet.as_view({"get": "list", "post": "create"})
service_detail = ServiceViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)
subservice_list = SubserviceViewSet.as_view({"get": "list", "post": "create"})
subservice_detail = SubserviceViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    path(
        "<uuid:organization_uuid>/services/",
        service_list,
        name="organization-service-list",
    ),
    path(
        "<uuid:organization_uuid>/services/<uuid:uuid>/",
        service_detail,
        name="organization-service-detail",
    ),
    path(
        "services/<uuid:service_uuid>/subservices/",
        subservice_list,
        name="organization-subservice-list",
    ),
    path(
        "services/<uuid:service_uuid>/subservices/<uuid:uuid>/",
        subservice_detail,
        name="organization-subservice-detail",
    ),
] + router.urls
