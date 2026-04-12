from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, viewsets

from common.throttling import ActionScopedRateThrottleMixin

from ..models import AllowedCity, Category, PlanTierCatalog, ServiceCatalog
from ..serializers import (
    AllowedCitySerializer,
    CategorySerializer,
    PlanTierCatalogSerializer,
    ServiceCatalogSerializer,
)


@extend_schema(tags=["Catalog"])
@extend_schema_view(
    list=extend_schema(
        tags=["Catalog"],
        summary="List allowed cities",
        description="Returns the public allowed cities catalog.",
        auth=[],
    ),
)
class AllowedCityViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AllowedCitySerializer
    permission_classes = [permissions.AllowAny]
    queryset = AllowedCity.objects.all().order_by("name")
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
    }


@extend_schema(tags=["Catalog"])
@extend_schema_view(
    list=extend_schema(
        tags=["Catalog"],
        summary="List categories",
        description="Returns the public categories catalog.",
        auth=[],
    ),
)
class CategoryViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    queryset = Category.objects.all().order_by("name")
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
    }


@extend_schema(tags=["Catalog"])
@extend_schema_view(
    list=extend_schema(
        tags=["Catalog"],
        summary="List services",
        description="Returns the public fixed services catalog.",
        auth=[],
    ),
)
class ServiceCatalogViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ServiceCatalogSerializer
    permission_classes = [permissions.AllowAny]
    queryset = ServiceCatalog.objects.select_related("category").order_by("name", "uuid")
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
    }


@extend_schema(tags=["Catalog"])
@extend_schema_view(
    list=extend_schema(
        tags=["Catalog"],
        summary="List plan tiers",
        description="Returns the public fixed plan tiers catalog.",
        auth=[],
    ),
)
class PlanTierCatalogViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PlanTierCatalogSerializer
    permission_classes = [permissions.AllowAny]
    queryset = PlanTierCatalog.objects.all().order_by("sort_order", "name")
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
    }
