from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from Core.permissions import IsActiveAccount
from Core.throttling import ActionScopedRateThrottleMixin
from jobs.models import Job
from organization.models import Organization

from .serializers import (
    ManagementJobSerializer,
    ManagementOrganizationSerializer,
    ManagementUserSerializer,
)


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


class ManagementUserViewSet(
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


class ManagementOrganizationViewSet(
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


class ManagementJobViewSet(
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
        "organization",
        "organization__user",
        "plan_price",
        "plan_price__subservice",
        "plan_price__subservice__service",
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
