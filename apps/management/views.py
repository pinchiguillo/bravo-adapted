import uuid

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.management.models import FeatureFlag
from apps.organization.models import AllowedCity, Announcement, Category, Organization, ServiceCatalog
from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from .serializers import (
    ManagementAllowedCitySerializer,
    ManagementAnnouncementSerializer,
    ManagementCategorySerializer,
    ManagementFeatureFlagSerializer,
    ManagementOrganizationSerializer,
    ManagementServiceCatalogSerializer,
    ManagementUserSerializer,
)

if apps.is_installed("apps.jobs"):
    from apps.jobs.models import Job

    from .serializers import ManagementJobSerializer


class ManagementStatusActionsMixin:
    status_serializer_class = None

    def _set_status(self, request, status_value):
        instance = self.get_object()
        instance.status = status_value
        instance.save(update_fields=["status"])
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="Activate managed resource")
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, *args, **kwargs):
        return self._set_status(request, self.status_serializer_class.ACTIVE)

    @extend_schema(summary="Deactivate managed resource")
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, *args, **kwargs):
        return self._set_status(request, self.status_serializer_class.INACTIVE)

    @extend_schema(summary="Suspend managed resource")
    @action(detail=True, methods=["post"], url_path="suspend")
    def suspend(self, request, *args, **kwargs):
        return self._set_status(request, self.status_serializer_class.SUSPENDED)


class ManagementFeatureFlagActionsMixin:
    def _set_active_state(self, is_active):
        instance = self.get_object()
        instance.is_active = is_active
        instance.save(update_fields=["is_active"])
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="Activate feature flag")
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, *args, **kwargs):
        return self._set_active_state(True)

    @extend_schema(summary="Deactivate feature flag")
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, *args, **kwargs):
        return self._set_active_state(False)


class ManagementBypassAdminLoginMixin:
    def get_permissions(self):
        if settings.BYPASS_ADMIN_LOGIN:
            return [permissions.AllowAny()]
        return super().get_permissions()


management_user_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Free text search over uuid, username, email, first name and last name.",
)

management_user_status_parameter = OpenApiParameter(
    name="status",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Exact user status filter.",
)

management_user_email_verified_parameter = OpenApiParameter(
    name="email_verified",
    type=bool,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Exact boolean filter for email verification status.",
)


@extend_schema(tags=["Management / Users"])
@extend_schema_view(
    list=extend_schema(
        tags=["Management / Users"],
        summary="List managed users",
        description="Returns the paginated list of managed users with optional search and filters.",
        parameters=[
            management_user_search_parameter,
            management_user_status_parameter,
            management_user_email_verified_parameter,
        ],
    ),
)
class ManagementUserViewSet(
    ManagementBypassAdminLoginMixin,
    ActionScopedRateThrottleMixin,
    ManagementStatusActionsMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementUserSerializer
    queryset = get_user_model().objects.all().order_by("id")
    lookup_field = "uuid"
    status_serializer_class = get_user_model().Status
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "activate": "management_status",
        "deactivate": "management_status",
        "suspend": "management_status",
    }

    def get_queryset(self):
        queryset = self.queryset
        if self.action != "list":
            return queryset

        search_query = str(self.request.query_params.get("search", "")).strip()
        if search_query:
            search_filter = (
                Q(username__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
            )
            search_uuid = self._parse_uuid(search_query)
            if search_uuid is not None:
                search_filter |= Q(uuid=search_uuid)
            queryset = queryset.filter(search_filter)

        status_value = str(self.request.query_params.get("status", "")).strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        email_verified = self.request.query_params.get("email_verified")
        if email_verified is not None and str(email_verified).strip() != "":
            queryset = queryset.filter(email_verified=self._parse_boolean_query_param(email_verified))

        return queryset

    def _parse_boolean_query_param(self, raw_value):
        normalized_value = str(raw_value).strip().lower()
        if normalized_value in {"true", "1"}:
            return True
        if normalized_value in {"false", "0"}:
            return False
        raise ValidationError(
            {"email_verified": "Use a boolean value: true or false."}
        )

    def _parse_uuid(self, raw_value):
        try:
            return uuid.UUID(str(raw_value).strip())
        except (AttributeError, TypeError, ValueError):
            return None


@extend_schema(tags=["Management / Feature Flags"])
class ManagementFeatureFlagViewSet(
    ManagementBypassAdminLoginMixin,
    ActionScopedRateThrottleMixin,
    ManagementFeatureFlagActionsMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementFeatureFlagSerializer
    queryset = FeatureFlag.objects.all().order_by("key")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "activate": "management_status",
        "deactivate": "management_status",
    }


@extend_schema(tags=["Management / Categories"])
class ManagementCategoryViewSet(
    ManagementBypassAdminLoginMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementCategorySerializer
    queryset = Category.objects.all().order_by("name")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
    }


@extend_schema(tags=["Management / Allowed Cities"])
class ManagementAllowedCityViewSet(
    ManagementBypassAdminLoginMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementAllowedCitySerializer
    queryset = AllowedCity.objects.all().order_by("name")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
    }


management_announcement_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Free text search over announcement title, description, location, category and services.",
)


management_announcement_status_parameter = OpenApiParameter(
    name="status",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Exact announcement status filter.",
)


@extend_schema(tags=["Management / Announcements"])
@extend_schema_view(
    list=extend_schema(
        tags=["Management / Announcements"],
        summary="List managed announcements",
        description="Returns the paginated list of announcements for administrative management.",
        parameters=[management_announcement_search_parameter, management_announcement_status_parameter],
    ),
)
class ManagementAnnouncementViewSet(
    ManagementBypassAdminLoginMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementAnnouncementSerializer
    queryset = Announcement.objects.select_related("organization", "category").prefetch_related(
        "images", "subservices__service_catalog__category", "subservices__price_table"
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
    }

    def get_queryset(self):
        queryset = self.queryset.order_by("-created_at", "-id")

        if self.action != "list":
            return queryset

        search_query = str(self.request.query_params.get("search", "")).strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(location__icontains=search_query)
                | Q(announcement__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(free_text__icontains=search_query)
                | Q(category__name__icontains=search_query)
                | Q(subservices__service_catalog__name__icontains=search_query)
                | Q(status__icontains=search_query)
            )

        status_value = str(self.request.query_params.get("status", "")).strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        return queryset.distinct()


@extend_schema(tags=["Management / Services"])
class ManagementServiceCatalogViewSet(
    ManagementBypassAdminLoginMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementServiceCatalogSerializer
    queryset = ServiceCatalog.objects.select_related("category").order_by("name", "uuid")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
    }


@extend_schema(tags=["Management / Organizations"])
class ManagementOrganizationViewSet(
    ManagementBypassAdminLoginMixin,
    ActionScopedRateThrottleMixin,
    ManagementStatusActionsMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementOrganizationSerializer
    queryset = Organization.objects.select_related("user").with_rating().order_by("name")
    lookup_field = "uuid"
    status_serializer_class = Organization.Status
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "activate": "management_status",
        "deactivate": "management_status",
        "suspend": "management_status",
    }


if apps.is_installed("apps.jobs"):
    @extend_schema(tags=["Management / Jobs"])
    class ManagementJobViewSet(
        ManagementBypassAdminLoginMixin,
        ActionScopedRateThrottleMixin,
        ManagementStatusActionsMixin,
        mixins.ListModelMixin,
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        mixins.UpdateModelMixin,
        viewsets.GenericViewSet,
    ):
        permission_classes = [IsActiveAccount, permissions.IsAdminUser]
        serializer_class = ManagementJobSerializer
        queryset = Job.objects.select_related(
            "user",
            "announcement",
            "announcement__organization",
            "announcement__organization__user",
            "plan_price",
            "plan_price__subservice",
            "plan_price__subservice__announcement",
            "plan_price__subservice__service_catalog",
        ).order_by("-created_at", "-id")
        lookup_field = "uuid"
        status_serializer_class = Job.Status
        throttle_scope_prefix = "management"
        throttle_scope_action_map = {
            "list": "management_read",
            "retrieve": "management_read",
            "create": "management_write",
            "update": "management_write",
            "partial_update": "management_write",
            "activate": "management_status",
            "deactivate": "management_status",
            "suspend": "management_status",
        }
