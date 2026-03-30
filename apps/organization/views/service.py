from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from ..models import Service, ServicePrice, Subservice
from ..permissions import IsOrganizationResourceOwner
from ..serializers import (
    PublicServicePriceSerializer,
    ServicePriceSerializer,
    ServiceSerializer,
    SubserviceSerializer,
)
from .common import (
    OrganizationVisibilityMixin,
    organization_uuid_parameter,
    service_price_uuid_parameter,
    service_uuid_parameter,
    subservice_uuid_parameter,
)


@extend_schema_view(
    list=extend_schema(
        summary="List services",
        description="Lists the services of the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
        auth=[],
    ),
    create=extend_schema(
        summary="Create service",
        description=(
            "Creates a service in the organization specified in the URL "
            "if it belongs to the authenticated user."
        ),
        parameters=[organization_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get service",
        description="Returns the details of a service belonging to the organization specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
        auth=[],
    ),
    update=extend_schema(
        summary="Replace service",
        description="Fully replaces a service in the organization specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update service",
        description="Partially updates a service in the organization specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete service",
        description="Deletes a service in the organization specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
)
class ServiceViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    viewsets.ModelViewSet,
):
    serializer_class = ServiceSerializer
    queryset = Service.objects.select_related("organization", "service_catalog", "category")
    lookup_field = "uuid"
    lookup_url_kwarg = "service_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
        "retrieve": "organization_public_read",
        "create": "organization_write",
        "update": "organization_write",
        "partial_update": "organization_write",
        "destroy": "organization_write",
    }

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [permissions.AllowAny()]
        if self.action in {"update", "partial_update", "destroy"}:
            return [IsActiveAccount(), IsOrganizationResourceOwner()]
        return [IsActiveAccount()]

    def get_queryset(self):
        queryset = self.queryset
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is not None:
            if self.action in {"list", "retrieve"}:
                self.require_visible_organization()
            queryset = queryset.filter(organization__uuid=organization_uuid)
        return queryset

    def _get_organization_from_url(self):
        organization = self.get_url_organization()
        if organization is None:
            raise NotFound("Organization not found.")
        return organization

    def perform_create(self, serializer):
        organization = self._get_organization_from_url()
        if organization.user_id != self.request.user.id:
            raise PermissionDenied("Organization does not belong to the authenticated user.")
        self.ensure_organization_is_approved_for_write(organization)
        serializer.save(organization=organization)

    def perform_update(self, serializer):
        self.ensure_organization_is_approved_for_write(serializer.instance.organization)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self.ensure_organization_is_approved_for_write(instance.organization)
        super().perform_destroy(instance)


@extend_schema_view(
    list=extend_schema(
        summary="List public subservices",
        description="Lists the public subservices of a service identified by organization UUID and service UUID.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
        auth=[],
    ),
    retrieve=extend_schema(
        summary="Get public subservice",
        description=(
            "Returns the details of a public subservice identified by "
            "organization UUID, service UUID and subservice UUID."
        ),
        parameters=[organization_uuid_parameter, service_uuid_parameter, subservice_uuid_parameter],
        auth=[],
    ),
)
class PublicSubserviceViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SubserviceSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Subservice.objects.select_related(
        "service",
        "service__organization",
    ).prefetch_related("price_table")
    lookup_field = "uuid"
    lookup_url_kwarg = "subservice_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
        "retrieve": "organization_public_read",
    }

    def get_queryset(self):
        organization = self.require_visible_organization()
        return self.queryset.filter(
            service__organization=organization,
            service__uuid=self.kwargs["service_uuid"],
        )


@extend_schema_view(
    list=extend_schema(
        summary="List subservices",
        description="Lists the subservices of the service specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
    create=extend_schema(
        summary="Create subservice",
        description="Creates a subservice associated with the service specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get subservice",
        description="Returns the details of a subservice belonging to the service specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace subservice",
        description="Fully replaces a subservice of the service specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update subservice",
        description="Partially updates a subservice of the service specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete subservice",
        description="Deletes a subservice of the service specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter],
    ),
)
class SubserviceViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    viewsets.ModelViewSet,
):
    serializer_class = SubserviceSerializer
    permission_classes = [IsActiveAccount]
    queryset = Subservice.objects.select_related("service", "service__organization").prefetch_related(
        "price_table"
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_authenticated_read",
        "retrieve": "organization_authenticated_read",
        "create": "organization_write",
        "update": "organization_write",
        "partial_update": "organization_write",
        "destroy": "organization_write",
    }

    def get_queryset(self):
        queryset = self.queryset.filter(service__organization__user=self.request.user)
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is not None:
            queryset = queryset.filter(service__organization__uuid=organization_uuid)
        service_uuid = self.kwargs.get("service_uuid")
        if service_uuid is not None:
            queryset = queryset.filter(service__uuid=service_uuid)
        return queryset

    def _get_service_from_url(self):
        organization_uuid = self.kwargs.get("organization_uuid")
        service_uuid = self.kwargs.get("service_uuid")
        service = Service.objects.select_related("organization", "service_catalog").filter(uuid=service_uuid)
        if organization_uuid is not None:
            service = service.filter(organization__uuid=organization_uuid)
        service = service.first()
        if service is None:
            raise NotFound("Service not found.")
        return service

    def perform_create(self, serializer):
        service = self._get_service_from_url()
        if service.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        self.ensure_organization_is_approved_for_write(service.organization)
        payload_service = serializer.validated_data["service"]
        if payload_service.uuid != service.uuid:
            raise ValidationError({"service": "Service must match the service in the URL."})
        serializer.save(service=service)

    def perform_update(self, serializer):
        service = self._get_service_from_url()
        if service.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        self.ensure_organization_is_approved_for_write(service.organization)
        payload_service = serializer.validated_data.get("service", serializer.instance.service)
        if payload_service.uuid != service.uuid:
            raise ValidationError({"service": "Service must match the service in the URL."})
        serializer.save(service=service)

    def perform_destroy(self, instance):
        self.ensure_organization_is_approved_for_write(instance.service.organization)
        super().perform_destroy(instance)


@extend_schema_view(
    list=extend_schema(
        summary="List service prices",
        description="Lists the service prices of the subservice specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter, subservice_uuid_parameter],
    ),
    create=extend_schema(
        summary="Create service price",
        description="Creates a service price for the subservice specified in the URL.",
        parameters=[organization_uuid_parameter, service_uuid_parameter, subservice_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get service price",
        description="Returns a service price belonging to the subservice specified in the URL.",
        parameters=[
            organization_uuid_parameter,
            service_uuid_parameter,
            subservice_uuid_parameter,
            service_price_uuid_parameter,
        ],
    ),
    update=extend_schema(
        summary="Replace service price",
        description="Fully replaces a service price belonging to the subservice specified in the URL.",
        parameters=[
            organization_uuid_parameter,
            service_uuid_parameter,
            subservice_uuid_parameter,
            service_price_uuid_parameter,
        ],
    ),
    partial_update=extend_schema(
        summary="Update service price",
        description="Partially updates a service price belonging to the subservice specified in the URL.",
        parameters=[
            organization_uuid_parameter,
            service_uuid_parameter,
            subservice_uuid_parameter,
            service_price_uuid_parameter,
        ],
    ),
    destroy=extend_schema(
        summary="Delete service price",
        description="Deletes a service price belonging to the subservice specified in the URL.",
        parameters=[
            organization_uuid_parameter,
            service_uuid_parameter,
            subservice_uuid_parameter,
            service_price_uuid_parameter,
        ],
    ),
)
class ServicePriceViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    viewsets.ModelViewSet,
):
    serializer_class = ServicePriceSerializer
    permission_classes = [IsActiveAccount]
    queryset = ServicePrice.objects.select_related(
        "subservice",
        "subservice__service",
        "subservice__service__organization",
    )
    lookup_field = "uuid"
    lookup_url_kwarg = "price_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_authenticated_read",
        "retrieve": "organization_authenticated_read",
        "create": "organization_write",
        "update": "organization_write",
        "partial_update": "organization_write",
        "destroy": "organization_write",
    }

    def get_queryset(self):
        queryset = self.queryset.filter(subservice__service__organization__user=self.request.user)
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is not None:
            queryset = queryset.filter(subservice__service__organization__uuid=organization_uuid)
        service_uuid = self.kwargs.get("service_uuid")
        if service_uuid is not None:
            queryset = queryset.filter(subservice__service__uuid=service_uuid)
        subservice_uuid = self.kwargs.get("subservice_uuid")
        if subservice_uuid is not None:
            self._get_subservice_from_url()
            queryset = queryset.filter(subservice__uuid=subservice_uuid)
        return queryset

    def _get_subservice_from_url(self):
        organization_uuid = self.kwargs.get("organization_uuid")
        service_uuid = self.kwargs.get("service_uuid")
        subservice_uuid = self.kwargs.get("subservice_uuid")
        subservice = Subservice.objects.select_related("service", "service__organization")
        subservice = subservice.filter(
            uuid=subservice_uuid,
            service__organization__user=self.request.user,
        )
        if organization_uuid is not None:
            subservice = subservice.filter(service__organization__uuid=organization_uuid)
        if service_uuid is not None:
            subservice = subservice.filter(service__uuid=service_uuid)
        subservice = subservice.first()
        if subservice is None:
            raise NotFound("Subservice not found.")
        return subservice

    def _get_subservice(self, serializer):
        subservice = self._get_subservice_from_url()
        if subservice.service.organization.user_id != self.request.user.id:
            raise PermissionDenied("Subservice does not belong to the authenticated user organization.")
        self.ensure_organization_is_approved_for_write(subservice.service.organization)
        payload_subservice = serializer.validated_data.get(
            "subservice",
            getattr(serializer.instance, "subservice", None),
        )
        if payload_subservice is None:
            payload_subservice = subservice
        if payload_subservice.uuid != subservice.uuid:
            raise ValidationError({"subservice": "Subservice must match the subservice in the URL."})
        return subservice

    def perform_create(self, serializer):
        subservice = self._get_subservice(serializer)
        serializer.save(subservice=subservice)

    def perform_update(self, serializer):
        subservice = self._get_subservice(serializer)
        serializer.save(subservice=subservice)

    def perform_destroy(self, instance):
        self.ensure_organization_is_approved_for_write(instance.subservice.service.organization)
        super().perform_destroy(instance)


@extend_schema_view(
    list=extend_schema(
        summary="List public service prices",
        description=(
            "Lists the public prices of a subservice identified by organization UUID, "
            "service UUID and subservice UUID."
        ),
        parameters=[organization_uuid_parameter, service_uuid_parameter, subservice_uuid_parameter],
        auth=[],
    ),
    retrieve=extend_schema(
        summary="Get public service price",
        description=(
            "Returns a public service price identified by organization UUID, service UUID, "
            "subservice UUID and price UUID."
        ),
        parameters=[
            organization_uuid_parameter,
            service_uuid_parameter,
            subservice_uuid_parameter,
            service_price_uuid_parameter,
        ],
        auth=[],
    ),
)
class PublicServicePriceViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PublicServicePriceSerializer
    permission_classes = [permissions.AllowAny]
    queryset = ServicePrice.objects.select_related(
        "subservice",
        "subservice__service",
        "subservice__service__organization",
    )
    lookup_field = "uuid"
    lookup_url_kwarg = "price_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
        "retrieve": "organization_public_read",
    }

    def get_queryset(self):
        organization = self.require_visible_organization()
        return self.queryset.filter(
            subservice__service__organization=organization,
            subservice__service__uuid=self.kwargs["service_uuid"],
            subservice__uuid=self.kwargs["subservice_uuid"],
        )
