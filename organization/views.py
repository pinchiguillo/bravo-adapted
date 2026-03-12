from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from Core.permissions import IsActiveAccount
from Core.throttling import ActionScopedRateThrottleMixin

from .models import Category, Organization, Service, ServicePrice, Subservice
from .permissions import IsOrganizationOwner, IsServiceOrganizationOwner
from .serializers import (
    CategorySerializer,
    OrganizationPublicSerializer,
    OrganizationSerializer,
    ServicePriceSerializer,
    ServiceSerializer,
    SubserviceSerializer,
)

service_price_uuid_parameter = OpenApiParameter(
    name="uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="Service price identifier.",
)

organization_uuid_parameter = OpenApiParameter(
    name="organization_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the organization that owns the service.",
)

service_uuid_parameter = OpenApiParameter(
    name="service_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the service that owns the subservice.",
)


@extend_schema_view(
    create=extend_schema(
        summary="Create organization",
        description="Creates an organization associated with the authenticated user.",
        request=OrganizationSerializer,
        responses={
            status.HTTP_201_CREATED: OrganizationSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Authenticated user already has an organization."
            ),
        },
    ),
    list=extend_schema(
        summary="List organizations",
        description="Lists all organizations. Only available to admin users.",
    ),
    retrieve=extend_schema(
        summary="Get organization",
        description="Returns the public details of an organization identified by UUID.",
    ),
    update=extend_schema(
        summary="Replace organization",
        description="Fully replaces an organization. Only allowed for its authenticated owner.",
    ),
    partial_update=extend_schema(
        summary="Update organization",
        description="Partially updates an organization. Only allowed for its authenticated owner.",
    ),
    destroy=extend_schema(
        summary="Delete organization",
        description="Deletes an organization. Only allowed for its authenticated owner.",
    ),
)
class OrganizationViewSet(
    ActionScopedRateThrottleMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.select_related("user")
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_admin",
        "create": "organization_write",
        "retrieve": "organization_public_read",
        "me": "organization_authenticated_read",
        "update_me": "organization_write",
        "update": "organization_write",
        "partial_update": "organization_write",
        "destroy": "organization_write",
    }

    def get_permissions(self):
        if self.action == "list":
            return [IsActiveAccount(), permissions.IsAdminUser()]
        if self.action == "retrieve":
            return [permissions.AllowAny()]
        if self.action in {"update", "partial_update", "destroy"}:
            return [IsActiveAccount(), IsOrganizationOwner()]
        return [IsActiveAccount()]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return OrganizationPublicSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        if Organization.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": "Authenticated user already has an organization."})
        serializer.save(user=self.request.user)

    @extend_schema(
        summary="Get my organization",
        description="Returns the organization associated with the authenticated user.",
    )
    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        organization = Organization.objects.filter(user=request.user).first()
        if organization is None:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(organization)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @me.mapping.patch
    @extend_schema(
        summary="Update my organization",
        description="Partially updates the organization associated with the authenticated user.",
    )
    def update_me(self, request):
        organization = Organization.objects.filter(user=request.user).first()
        if organization is None:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="List categories",
        description="Returns the categories catalog available to authenticated users.",
    ),
    retrieve=extend_schema(
        summary="Get category",
        description="Returns the details of a category identified by UUID.",
    ),
)
class CategoryViewSet(ActionScopedRateThrottleMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsActiveAccount]
    queryset = Category.objects.all()
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_authenticated_read",
        "retrieve": "organization_authenticated_read",
    }


@extend_schema_view(
    list=extend_schema(
        summary="List services",
        description="Lists the services of the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
    ),
    create=extend_schema(
        summary="Create service",
        description="Creates a service in the organization specified in the URL if it belongs to the authenticated user.",
        parameters=[organization_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get service",
        description="Returns the details of a service belonging to the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace service",
        description="Fully replaces a service in the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update service",
        description="Partially updates a service in the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete service",
        description="Deletes a service in the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
    ),
)
class ServiceViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    queryset = Service.objects.select_related("organization")
    lookup_field = "uuid"
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
            return [IsActiveAccount(), IsServiceOrganizationOwner()]
        return [IsActiveAccount()]

    def get_queryset(self):
        queryset = self.queryset
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is not None:
            queryset = queryset.filter(organization__uuid=organization_uuid)
        return queryset

    def _get_organization_from_url(self):
        organization_uuid = self.kwargs.get("organization_uuid")
        organization = Organization.objects.filter(uuid=organization_uuid).first()
        if organization is None:
            raise NotFound("Organization not found.")
        return organization

    def perform_create(self, serializer):
        organization = self._get_organization_from_url()
        if organization.user_id != self.request.user.id:
            raise PermissionDenied("Organization does not belong to the authenticated user.")
        serializer.save(organization=organization)


@extend_schema_view(
    list=extend_schema(
        summary="List subservices",
        description="Lists the subservices of the service specified in the URL.",
        parameters=[service_uuid_parameter],
    ),
    create=extend_schema(
        summary="Create subservice",
        description="Creates a subservice associated with the service specified in the URL.",
        parameters=[service_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get subservice",
        description="Returns the details of a subservice belonging to the service specified in the URL.",
        parameters=[service_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace subservice",
        description="Fully replaces a subservice of the service specified in the URL.",
        parameters=[service_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update subservice",
        description="Partially updates a subservice of the service specified in the URL.",
        parameters=[service_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete subservice",
        description="Deletes a subservice of the service specified in the URL.",
        parameters=[service_uuid_parameter],
    ),
)
class SubserviceViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = SubserviceSerializer
    permission_classes = [IsActiveAccount]
    queryset = Subservice.objects.select_related("service", "service__organization")
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
        service_uuid = self.kwargs.get("service_uuid")
        if service_uuid is not None:
            queryset = queryset.filter(service__uuid=service_uuid)
        return queryset

    def _get_service_from_url(self):
        service_uuid = self.kwargs.get("service_uuid")
        service = Service.objects.select_related("organization").filter(uuid=service_uuid).first()
        if service is None:
            raise NotFound("Service not found.")
        return service

    def perform_create(self, serializer):
        service = self._get_service_from_url()
        if service.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        payload_service = serializer.validated_data["service"]
        if payload_service.uuid != service.uuid:
            raise ValidationError({"service": "Service must match the service in the URL."})
        serializer.save(service=service)

    def perform_update(self, serializer):
        service = self._get_service_from_url()
        if service.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        payload_service = serializer.validated_data.get("service", serializer.instance.service)
        if payload_service.uuid != service.uuid:
            raise ValidationError({"service": "Service must match the service in the URL."})
        serializer.save(service=service)


@extend_schema_view(
    list=extend_schema(
        summary="List service prices",
        description="Lists configured prices for services in the authenticated user's organization.",
    ),
    create=extend_schema(
        summary="Create service price",
        description="Creates a price for a service in the authenticated user's organization.",
    ),
    retrieve=extend_schema(
        summary="Get service price",
        description="Returns the details of a service price accessible by the authenticated user.",
        parameters=[service_price_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace service price",
        description="Fully replaces a service price in the authenticated user's organization.",
        parameters=[service_price_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update service price",
        description="Partially updates a service price in the authenticated user's organization.",
        parameters=[service_price_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete service price",
        description="Deletes a service price in the authenticated user's organization.",
        parameters=[service_price_uuid_parameter],
    ),
)
class ServicePriceViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = ServicePriceSerializer
    permission_classes = [IsActiveAccount]
    queryset = ServicePrice.objects.select_related("service", "service__organization")
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
        return self.queryset.filter(service__organization__user=self.request.user)

    def perform_create(self, serializer):
        service = serializer.validated_data["service"]
        if service.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        serializer.save()

    def perform_update(self, serializer):
        service = serializer.validated_data.get("service", serializer.instance.service)
        if service.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        serializer.save()
