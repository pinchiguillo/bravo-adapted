from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from ..models import Organization
from ..permissions import IsOrganizationResourceOwner
from ..serializers import OrganizationPublicSerializer, OrganizationSerializer
from .common import OrganizationSearchMixin, organization_search_parameter


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
    retrieve=extend_schema(
        summary="Get organization",
        description="Returns the public details of an organization identified by UUID.",
        auth=[],
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
    OrganizationSearchMixin,
    ActionScopedRateThrottleMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.select_related("user").with_rating()
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "create": "organization_write",
        "retrieve": "organization_public_read",
        "me": "organization_authenticated_read",
        "update_me": "organization_write",
        "update": "organization_write",
        "partial_update": "organization_write",
        "destroy": "organization_write",
    }

    def get_permissions(self):
        if self.action == "retrieve":
            return [permissions.AllowAny()]
        if self.action in {"update", "partial_update", "destroy"}:
            return [IsActiveAccount(), IsOrganizationResourceOwner()]
        return [IsActiveAccount()]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return OrganizationPublicSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        if Organization.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": "Authenticated user already has an organization."})
        serializer.save(user=self.request.user)

    def get_object(self):
        organization = super().get_object()
        if self.action != "retrieve":
            return organization

        user = getattr(self.request, "user", None)
        if organization.is_validated:
            return organization
        if user is not None and user.is_authenticated and (
            user.is_staff or organization.user_id == user.id
        ):
            return organization
        raise NotFound("Organization not found.")

    def partial_update(self, request, *args, **kwargs):
        organization = self.get_object()
        serializer = self.get_serializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get my organization",
        description="Returns the organization associated with the authenticated user.",
    )
    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        organization = (
            Organization.objects.select_related("user").with_rating().filter(user=request.user).first()
        )
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
        organization = (
            Organization.objects.select_related("user").with_rating().filter(user=request.user).first()
        )
        if organization is None:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="Search organizations",
        description="Searches organizations. Only available to admin users.",
        parameters=[organization_search_parameter],
    ),
)
class OrganizationSearchViewSet(
    OrganizationSearchMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.select_related("user").with_rating()
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_admin",
    }

    def get_queryset(self):
        return self.filter_organizations_by_search(self.queryset).order_by("name")
