from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
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
    description="Identificador del precio de servicio.",
)

organization_uuid_parameter = OpenApiParameter(
    name="organization_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID de la organizacion propietaria del servicio.",
)

service_uuid_parameter = OpenApiParameter(
    name="service_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID del servicio propietario del subservicio.",
)


@extend_schema_view(
    list=extend_schema(
        summary="Listar organizaciones",
        description="Lista todas las organizaciones. Solo disponible para usuarios administradores.",
    ),
    retrieve=extend_schema(
        summary="Obtener organizacion",
        description="Devuelve el detalle publico de una organizacion identificada por su UUID.",
    ),
    update=extend_schema(
        summary="Reemplazar organizacion",
        description="Reemplaza completamente una organizacion. Solo permitido a su propietario autenticado.",
    ),
    partial_update=extend_schema(
        summary="Actualizar organizacion",
        description="Actualiza parcialmente una organizacion. Solo permitido a su propietario autenticado.",
    ),
    destroy=extend_schema(
        summary="Eliminar organizacion",
        description="Elimina una organizacion. Solo permitido a su propietario autenticado.",
    ),
)
class OrganizationViewSet(
    ActionScopedRateThrottleMixin,
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

    @extend_schema(
        summary="Obtener mi organizacion",
        description="Devuelve la organizacion asociada al usuario autenticado.",
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
        summary="Actualizar mi organizacion",
        description="Actualiza parcialmente la organizacion asociada al usuario autenticado.",
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
        summary="Listar categorias",
        description="Devuelve el catalogo de categorias disponible para usuarios autenticados.",
    ),
    retrieve=extend_schema(
        summary="Obtener categoria",
        description="Devuelve el detalle de una categoria identificada por su UUID.",
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
        summary="Listar servicios",
        description="Lista los servicios de la organizacion indicada en la URL.",
        parameters=[organization_uuid_parameter],
    ),
    create=extend_schema(
        summary="Crear servicio",
        description="Crea un servicio dentro de la organizacion indicada en la URL si pertenece al usuario autenticado.",
        parameters=[organization_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Obtener servicio",
        description="Devuelve el detalle de un servicio perteneciente a la organizacion indicada en la URL.",
        parameters=[organization_uuid_parameter],
    ),
    update=extend_schema(
        summary="Reemplazar servicio",
        description="Reemplaza completamente un servicio de la organizacion indicada en la URL.",
        parameters=[organization_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Actualizar servicio",
        description="Actualiza parcialmente un servicio de la organizacion indicada en la URL.",
        parameters=[organization_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Eliminar servicio",
        description="Elimina un servicio de la organizacion indicada en la URL.",
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
        summary="Listar subservicios",
        description="Lista los subservicios del servicio indicado en la URL.",
        parameters=[service_uuid_parameter],
    ),
    create=extend_schema(
        summary="Crear subservicio",
        description="Crea un subservicio asociado al servicio indicado en la URL.",
        parameters=[service_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Obtener subservicio",
        description="Devuelve el detalle de un subservicio perteneciente al servicio indicado en la URL.",
        parameters=[service_uuid_parameter],
    ),
    update=extend_schema(
        summary="Reemplazar subservicio",
        description="Reemplaza completamente un subservicio del servicio indicado en la URL.",
        parameters=[service_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Actualizar subservicio",
        description="Actualiza parcialmente un subservicio del servicio indicado en la URL.",
        parameters=[service_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Eliminar subservicio",
        description="Elimina un subservicio del servicio indicado en la URL.",
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
        summary="Listar precios de servicio",
        description="Lista los precios configurados para servicios de la organizacion del usuario autenticado.",
    ),
    create=extend_schema(
        summary="Crear precio de servicio",
        description="Crea un precio para un servicio de la organizacion del usuario autenticado.",
    ),
    retrieve=extend_schema(
        summary="Obtener precio de servicio",
        description="Devuelve el detalle de un precio de servicio accesible por el usuario autenticado.",
        parameters=[service_price_uuid_parameter],
    ),
    update=extend_schema(
        summary="Reemplazar precio de servicio",
        description="Reemplaza completamente un precio de servicio de la organizacion del usuario autenticado.",
        parameters=[service_price_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Actualizar precio de servicio",
        description="Actualiza parcialmente un precio de servicio de la organizacion del usuario autenticado.",
        parameters=[service_price_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Eliminar precio de servicio",
        description="Elimina un precio de servicio de la organizacion del usuario autenticado.",
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
