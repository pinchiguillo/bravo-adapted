import base64

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from ..models import Announcement, AnnouncementImage, Organization
from ..permissions import IsOrganizationResourceOwner
from ..serializers import (
    AnnouncementImageBase64Serializer,
    AnnouncementImageSerializer,
    AnnouncementImageUploadCompleteSerializer,
    AnnouncementImageUploadRequestSerializer,
    AnnouncementImageUploadTargetSerializer,
    AnnouncementSerializer,
)
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


@extend_schema(tags=["Announcements"])
@extend_schema_view(
    list=extend_schema(
        tags=["Announcements"],
        summary="List public announcements",
        description=(
            "Lists active announcements. Supports optional filtering by title, "
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
        .prefetch_related("images", "subservices__service_catalog__category", "subservices__price_table")
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


@extend_schema(tags=["Announcements"])
@extend_schema_view(
    retrieve=extend_schema(
        tags=["Announcements"],
        summary="Get public announcement",
        description="Returns the details of an active public announcement by announcement UUID.",
        parameters=[announcement_uuid_parameter],
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
        .prefetch_related("images", "subservices__service_catalog__category", "subservices__price_table")
        .filter(status=Announcement.Status.ACTIVE)
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "retrieve": "organization_public_read",
    }

    def get_queryset(self):
        return self.queryset.filter(
            **Organization.validated_filter_kwargs(prefix="organization__"),
        )


@extend_schema(tags=["Announcements"])
@extend_schema_view(
    list=extend_schema(
        tags=["Announcements"],
        summary="List announcements",
        description=(
            "Lists announcements for the organization specified in the URL. Supports "
            "optional filtering by title, category, service, status, text fields, "
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
        tags=["Announcements"],
        summary="Create announcement",
        description="Creates an announcement with optional subservices.",
        parameters=[organization_uuid_parameter],
        request=AnnouncementSerializer,
    ),
    update=extend_schema(
        tags=["Announcements"],
        summary="Replace announcement",
        description="Fully replaces an announcement owned by the organization specified in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
    partial_update=extend_schema(
        tags=["Announcements"],
        summary="Update announcement",
        description="Partially updates an announcement owned by the organization specified in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
    destroy=extend_schema(
        tags=["Announcements"],
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
        "title": "announcement",
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
        "subservices__service_catalog__name",
        "status",
    )
    search_uuid_fields = ("uuid", "category__uuid", "subservices__service_catalog__uuid")

    serializer_class = AnnouncementSerializer
    permission_classes = [IsActiveAccount]
    queryset = Announcement.objects.select_related("organization", "category").prefetch_related(
        "images", "subservices__service_catalog__category", "subservices__price_table"
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_authenticated_read",
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
                ("service", "services", "subservices__service_catalog__uuid"),
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


@extend_schema_view(
    list=extend_schema(
        summary="List announcement images",
        description="Lists images attached to an announcement owned by the organization in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
    create=extend_schema(
        summary="Prepare announcement image upload",
        description=(
            "Validates image metadata for an announcement owned by the organization "
            "in the URL and returns a signed URL so the client can upload the file "
            "directly to S3-compatible storage."
        ),
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
        request=AnnouncementImageUploadRequestSerializer,
        responses={status.HTTP_201_CREATED: AnnouncementImageUploadTargetSerializer},
    ),
    complete_upload=extend_schema(
        summary="Complete announcement image upload",
        description=(
            "Confirms a previously prepared direct upload after the client has "
            "uploaded the binary to S3-compatible storage."
        ),
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
        request=AnnouncementImageUploadCompleteSerializer,
        responses={status.HTTP_201_CREATED: AnnouncementImageSerializer},
    ),
    destroy=extend_schema(
        summary="Delete announcement image",
        description="Deletes an image from an announcement owned by the organization in the URL.",
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
)
class AnnouncementImageViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AnnouncementImageSerializer
    permission_classes = [IsActiveAccount]
    lookup_field = "uuid"
    lookup_url_kwarg = "image_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_authenticated_read",
        "create": "organization_write",
        "destroy": "organization_write",
    }

    def get_queryset(self):
        announcement = self._get_announcement()
        return AnnouncementImage.objects.filter(announcement=announcement)

    def get_permissions(self):
        if self.action == "destroy":
            return [IsActiveAccount(), IsOrganizationResourceOwner()]
        return [IsActiveAccount()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        organization = self.get_url_organization()
        if organization is not None:
            context["organization"] = organization
        return context

    def create(self, request, *args, **kwargs):
        announcement = self._get_announcement(for_write=True)
        serializer = AnnouncementImageUploadRequestSerializer(
            data=request.data,
            context={
                **self.get_serializer_context(),
                "announcement": announcement,
            },
        )
        serializer.is_valid(raise_exception=True)
        upload_target = serializer.save()
        response_serializer = AnnouncementImageUploadTargetSerializer(
            upload_target,
            context=self.get_serializer_context(),
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def complete_upload(self, request, *args, **kwargs):
        announcement = self._get_announcement(for_write=True)
        serializer = AnnouncementImageUploadCompleteSerializer(
            data=request.data,
            context={
                **self.get_serializer_context(),
                "announcement": announcement,
            },
        )
        serializer.is_valid(raise_exception=True)
        image = serializer.save()
        response_serializer = self.get_serializer(image)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        announcement = self._get_announcement(for_write=True)
        if instance.announcement_id != announcement.id:
            raise NotFound("Announcement image not found.")
        instance.delete()

    def _get_announcement(self, for_write=False):
        organization = self.get_url_organization()
        if organization is None:
            raise NotFound("Organization not found.")

        user = self.request.user
        if not (getattr(user, "is_staff", False) or organization.user_id == user.id):
            raise NotFound("Organization not found.")

        announcement = (
            Announcement.objects.select_related("organization")
            .filter(uuid=self.kwargs["uuid"], organization=organization)
            .first()
        )
        if announcement is None:
            raise NotFound("Announcement not found.")

        if for_write and not getattr(user, "is_staff", False):
            self.ensure_organization_is_approved_for_write(organization)

        return announcement


class AnnouncementImageBase64ResponseMixin:
    serializer_class = AnnouncementImageBase64Serializer

    def _build_base64_response(self, image):
        with image.image.open("rb") as image_file:
            encoded_data = base64.b64encode(image_file.read()).decode("ascii")

        serializer = self.get_serializer(image, context={"encoded_data": encoded_data})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["Announcements"])
@extend_schema_view(
    retrieve=extend_schema(
        tags=["Announcements"],
        summary="Get public announcement image as base64",
        description=(
            "Reads an image from the active public announcement and returns its content "
            "encoded as base64."
        ),
        parameters=[announcement_uuid_parameter],
        auth=[],
    ),
)
class PublicAnnouncementImageBase64ViewSet(
    AnnouncementImageBase64ResponseMixin,
    ActionScopedRateThrottleMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [permissions.AllowAny]
    queryset = AnnouncementImage.objects.select_related("announcement", "announcement__organization").filter(
        announcement__status=Announcement.Status.ACTIVE,
        **Organization.validated_filter_kwargs(prefix="announcement__organization__"),
    )
    lookup_field = "uuid"
    lookup_url_kwarg = "image_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {"retrieve": "organization_public_read"}

    def get_object(self):
        image = (
            self.get_queryset()
            .filter(announcement__uuid=self.kwargs["uuid"], uuid=self.kwargs["image_uuid"])
            .first()
        )
        if image is None:
            raise NotFound("Announcement image not found.")
        return image

    def retrieve(self, request, *args, **kwargs):
        return self._build_base64_response(self.get_object())


@extend_schema(tags=["Announcements"])
@extend_schema_view(
    retrieve=extend_schema(
        tags=["Announcements"],
        summary="Get announcement image as base64",
        description=(
            "Reads an image from an announcement owned by the organization in the URL "
            "and returns its content encoded as base64."
        ),
        parameters=[organization_uuid_parameter, announcement_uuid_parameter],
    ),
)
class OrganizationAnnouncementImageBase64ViewSet(
    AnnouncementImageBase64ResponseMixin,
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount]
    queryset = AnnouncementImage.objects.select_related("announcement", "announcement__organization")
    lookup_field = "uuid"
    lookup_url_kwarg = "image_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {"retrieve": "organization_authenticated_read"}

    def get_object(self):
        organization = self.get_url_organization()
        if organization is None:
            raise NotFound("Organization not found.")

        user = self.request.user
        if not (getattr(user, "is_staff", False) or organization.user_id == user.id):
            raise NotFound("Organization not found.")

        image = (
            self.queryset.filter(
                announcement__organization=organization,
                announcement__uuid=self.kwargs["uuid"],
                uuid=self.kwargs["image_uuid"],
            )
            .first()
        )
        if image is None:
            raise NotFound("Announcement image not found.")
        return image

    def retrieve(self, request, *args, **kwargs):
        return self._build_base64_response(self.get_object())
