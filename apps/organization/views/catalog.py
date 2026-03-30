from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import NotFound

from common.throttling import ActionScopedRateThrottleMixin

from ..models import Category, ServiceCatalog
from ..serializers import CategorySerializer, ServiceCatalogSerializer
from .common import category_uuid_parameter


@extend_schema_view(
    list=extend_schema(
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


@extend_schema_view(
    list=extend_schema(
        summary="List services by category",
        description="Returns the public services catalog filtered by category UUID.",
        parameters=[category_uuid_parameter],
        auth=[],
    ),
)
class CategoryServiceViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ServiceCatalogSerializer
    permission_classes = [permissions.AllowAny]
    queryset = ServiceCatalog.objects.select_related("category")
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
    }

    def get_queryset(self):
        category_uuid = self.kwargs["category_uuid"]
        if not Category.objects.filter(uuid=category_uuid).exists():
            raise NotFound("Category not found.")
        return self.queryset.filter(category__uuid=category_uuid).order_by("name", "uuid")
