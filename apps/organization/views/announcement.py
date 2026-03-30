from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from ..models import Announcement, Organization
from ..permissions import IsOrganizationResourceOwner
from ..serializers import AnnouncementSerializer
from .common import (
    AnnouncementPublicFilterMixin,
    AnnouncementQueryParamFilterMixin,
    OrganizationVisibilityMixin,
    announcement_categories_parameter,
    announcement_category_parameter,
    announcement_description_parameter,
    announcement_free_text_parameter,
    announcement_has_coordinates_parameter,
    announcement_location_parameter,
    announcement_name_parameter,
    announcement_organization_parameter,
    announcement_organizations_parameter,
    announcement_search_parameter,
    announcement_service_parameter,
    announcement_services_parameter,
    announcement_status_parameter,
    announcement_statuses_parameter,
    announcement_text_parameter,
    announcement_uuid_parameter,
    announcement_uuid_query_parameter,
    organization_uuid_parameter,
)


@extend_schema_view(
    list=extend_schema(
        summary="List public announcements",
        description=(
            "Lists active announcements. Supports optional filtering by announcement, "
            "organization, category, service, text fields, coordinates presence and "
            "plain text search."
        ),
        parameters=[
            announcement_uuid_query_parameter,
            announcement_organization_parameter,
            announcement_organizations_parameter,
            announcement_categories_parameter,
            announcement_category_parameter,
            announcement_service_parameter,
            announcement_services_parameter,
            announcement_name_parameter,
            announcement_location_parameter,
            announcement_text_parameter,
            announcement_description_parameter,
            announcement_free_text_parameter,
            announcement_has_coordinates_parameter,
            announcement_search_parameter,
        ],
        auth=[],
    ),
)
class PublicAnnouncementViewSet(
    AnnouncementPublicFilterMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.AllowAny]
    queryset = (
        Announcement.objects.select_related("organization", "category")
        .prefetch_related("services")
        .filter(
            status=Announcement.Status.ACTIVE,
            **Organization.validated_filter_kwargs(prefix="organization__"),
        )
    )
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
    }

    def get_queryset(self):
        return self.filter_announcements(self.queryset).order_by("-created_at", "-id")


@extend_schema_view(
    retrieve=extend_schema(
        summary="Get public announcement",
        description="Returns the details of an active public announcement by organization UUID and announcement UUID.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
        auth=[],
    ),
)
class PublicAnnouncementDetailViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.AllowAny]
    queryset = (
        Announcement.objects.select_related("organization", "category")
        .prefetch_related("services")
        .filter(status=Announcement.Status.ACTIVE)
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "retrieve": "organization_public_read",
    }

    def get_queryset(self):
        organization = self.require_visible_organization()
        return self.queryset.filter(organization=organization)


@extend_schema_view(
    list=extend_schema(
        summary="List announcements",
        description=(
            "Lists announcements for the organization specified in the URL. Supports "
            "optional filtering by announcement, category, service, status, text fields, "
            "coordinates presence and plain text search."
        ),
        parameters=[
            organization_uuid_parameter,
            announcement_uuid_query_parameter,
            announcement_categories_parameter,
            announcement_category_parameter,
            announcement_service_parameter,
            announcement_services_parameter,
            announcement_status_parameter,
            announcement_statuses_parameter,
            announcement_name_parameter,
            announcement_location_parameter,
            announcement_text_parameter,
            announcement_description_parameter,
            announcement_free_text_parameter,
            announcement_has_coordinates_parameter,
            announcement_search_parameter,
        ],
    ),
    create=extend_schema(
        summary="Create announcement",
        description="Creates an announcement for the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get announcement",
        description="Returns the details of an announcement belonging to the organization specified in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace announcement",
        description="Fully replaces an announcement owned by the organization specified in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update announcement",
        description="Partially updates an announcement owned by the organization specified in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete announcement",
        description="Deletes an announcement owned by the organization specified in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
)
class AnnouncementViewSet(
    AnnouncementQueryParamFilterMixin,
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    viewsets.ModelViewSet,
):
    text_filter_fields = {
        "name": "name",
        "location": "location",
        "announcement": "announcement",
        "description": "description",
        "free_text": "free_text",
    }
    search_fields = (
        "name",
        "location",
        "announcement",
        "description",
        "free_text",
        "category__name",
        "services__name",
        "status",
    )
    search_uuid_fields = ("uuid", "category__uuid", "services__uuid")

    serializer_class = AnnouncementSerializer
    permission_classes = [IsActiveAccount]
    queryset = Announcement.objects.select_related("organization", "category").prefetch_related("services")
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

    def get_permissions(self):
        if self.action in {"update", "partial_update", "destroy"}:
            return [IsActiveAccount(), IsOrganizationResourceOwner()]
        return [IsActiveAccount()]

    def get_queryset(self):
        queryset = self.queryset
        organization = self.get_url_organization()
        if organization is not None:
            user = self.request.user
            if not (user.is_staff or organization.user_id == user.id):
                raise NotFound("Organization not found.")
            queryset = queryset.filter(organization=organization)
        queryset = self._apply_uuid_filters(
            queryset,
            (
                ("uuid", "uuids", "uuid"),
                ("category", "categories", "category__uuid"),
                ("service", "services", "services__uuid"),
                ("status", "statuses", "status"),
            ),
        )
        queryset = self._apply_text_filters(queryset)
        queryset = self._apply_has_coordinates_filter(queryset)
        queryset = self._apply_search_filter(queryset, self.search_fields, self.search_uuid_fields)
        return queryset.distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        organization = self.get_url_organization()
        if organization is not None:
            context["organization"] = organization
        return context

    def _get_organization_from_url(self):
        return self.get_url_organization()

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
