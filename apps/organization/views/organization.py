from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from ..models import Organization
from ..serializers import OrganizationPublicSerializer, OrganizationSerializer


@extend_schema(tags=["Organizations"])
@extend_schema_view(
    create=extend_schema(
        tags=["Organizations"],
        summary="Create organization",
        description="Creates an organization associated with the authenticated user.",
        request=OrganizationSerializer,
        responses={
            status.HTTP_201_CREATED: OrganizationSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(description="Authenticated user already has an organization."),
        },
    ),
    retrieve=extend_schema(
        tags=["Organizations"],
        summary="Get organization",
        description="Returns the public details of an organization identified by UUID.",
        auth=[],
    ),
)
class OrganizationViewSet(
    ActionScopedRateThrottleMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationSerializer
    queryset = (
        Organization.objects.select_related(
            "user",
            "pricing",
            "pricing__plan_tier",
            "availability_settings",
        )
        .prefetch_related(
            "availability_settings__weekly_schedule",
            "availability_settings__exceptions",
        )
        .with_rating()
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "create": "organization_write",
        "retrieve": "organization_public_read",
        "me": "organization_authenticated_read",
        "update_me": "organization_write",
        "destroy_me": "organization_write",
    }

    def get_permissions(self):
        if self.action == "retrieve":
            return [permissions.AllowAny()]
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
        if user is not None and user.is_authenticated and (user.is_staff or organization.user_id == user.id):
            return organization
        raise NotFound("Organization not found.")

    def _get_authenticated_user_organization(self, user):
        return (
            Organization.objects.select_related(
                "user",
                "pricing",
                "pricing__plan_tier",
                "availability_settings",
            )
            .prefetch_related(
                "availability_settings__weekly_schedule",
                "availability_settings__exceptions",
            )
            .with_rating()
            .filter(user=user)
            .first()
        )

    @extend_schema(
        tags=["Organizations"],
        summary="Get my organization",
        description="Returns the organization associated with the authenticated user.",
    )
    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        organization = self._get_authenticated_user_organization(request.user)
        if organization is None:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(organization)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @me.mapping.patch
    @extend_schema(
        tags=["Organizations"],
        summary="Update my organization",
        description="Partially updates the organization associated with the authenticated user.",
    )
    def update_me(self, request):
        organization = self._get_authenticated_user_organization(request.user)
        if organization is None:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @me.mapping.delete
    @extend_schema(
        tags=["Organizations"],
        summary="Delete my organization",
        description="Deletes the organization associated with the authenticated user.",
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    def destroy_me(self, request):
        organization = self._get_authenticated_user_organization(request.user)
        if organization is None:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        organization.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
