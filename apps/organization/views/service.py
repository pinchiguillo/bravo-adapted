from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from ..models import Announcement, ServicePrice, Subservice
from ..serializers import (
    PublicServicePriceSerializer,
    ServicePriceSerializer,
    SubserviceSerializer,
)
from .common import (
    OrganizationVisibilityMixin,
    announcement_nested_uuid_parameter,
    service_price_uuid_parameter,
    subservice_uuid_parameter,
)


@extend_schema(tags=["Services"])
@extend_schema_view(
    list=extend_schema(
        tags=["Services"],
        summary="List public subservices",
        description="Lists the public subservices of an announcement identified by announcement UUID.",
        parameters=[announcement_nested_uuid_parameter],
        auth=[],
    ),
    retrieve=extend_schema(
        tags=["Services"],
        summary="Get public subservice",
        description=(
            "Returns the details of a public subservice identified by "
            "announcement UUID and subservice UUID."
        ),
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter],
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
        "announcement",
        "announcement__organization",
        "service_catalog",
        "service_catalog__category",
    ).prefetch_related("price_table")
    lookup_field = "uuid"
    lookup_url_kwarg = "subservice_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
        "retrieve": "organization_public_read",
    }

    def _get_visible_announcement(self):
        announcement = Announcement.objects.select_related("organization").filter(
            uuid=self.kwargs["announcement_uuid"]
        ).first()
        if announcement is None:
            raise NotFound("Announcement not found.")
        if not self.can_access_unapproved_organization(announcement.organization):
            raise NotFound("Announcement not found.")
        return announcement

    def get_queryset(self):
        return self.queryset.filter(
            announcement=self._get_visible_announcement(),
        )


@extend_schema(tags=["Services"])
@extend_schema_view(
    list=extend_schema(
        tags=["Services"],
        summary="List subservices",
        description="Lists the subservices of the announcement specified in the URL.",
        parameters=[announcement_nested_uuid_parameter],
        auth=[],
    ),
    create=extend_schema(
        tags=["Services"],
        summary="Create subservice",
        description="Creates a subservice associated with the announcement specified in the URL.",
        parameters=[announcement_nested_uuid_parameter],
    ),
    retrieve=extend_schema(
        tags=["Services"],
        summary="Get subservice",
        description="Returns the details of a subservice belonging to the announcement specified in the URL.",
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter],
        auth=[],
    ),
    update=extend_schema(
        tags=["Services"],
        summary="Replace subservice",
        description="Fully replaces a subservice of the announcement specified in the URL.",
        parameters=[announcement_nested_uuid_parameter],
    ),
    partial_update=extend_schema(
        tags=["Services"],
        summary="Update subservice",
        description="Partially updates a subservice of the announcement specified in the URL.",
        parameters=[announcement_nested_uuid_parameter],
    ),
    destroy=extend_schema(
        tags=["Services"],
        summary="Delete subservice",
        description="Deletes a subservice of the announcement specified in the URL.",
        parameters=[announcement_nested_uuid_parameter],
    ),
)
class SubserviceViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    viewsets.ModelViewSet,
):
    serializer_class = SubserviceSerializer
    queryset = Subservice.objects.select_related(
        "announcement",
        "announcement__organization",
        "service_catalog",
        "service_catalog__category",
    ).prefetch_related("price_table")
    lookup_field = "uuid"
    lookup_url_kwarg = "subservice_uuid"
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
        return [IsActiveAccount()]

    def get_queryset(self):
        queryset = self.queryset
        announcement_uuid = self.kwargs.get("announcement_uuid")
        if announcement_uuid is not None:
            if self.action in {"list", "retrieve"}:
                announcement = self._get_announcement_from_url()
                if not self.can_access_unapproved_organization(announcement.organization):
                    raise NotFound("Announcement not found.")
                queryset = queryset.filter(announcement=announcement)
            else:
                queryset = queryset.filter(
                    announcement__uuid=announcement_uuid,
                    announcement__organization__user=self.request.user,
                )
            queryset = queryset.filter(announcement__uuid=announcement_uuid)
        return queryset

    def _get_announcement_from_url(self):
        announcement_uuid = self.kwargs.get("announcement_uuid")
        announcement = Announcement.objects.select_related("organization").filter(uuid=announcement_uuid)
        announcement = announcement.first()
        if announcement is None:
            raise NotFound("Announcement not found.")
        return announcement

    def perform_create(self, serializer):
        announcement = self._get_announcement_from_url()
        if announcement.organization.user_id != self.request.user.id:
            raise PermissionDenied(
                "Announcement does not belong to the authenticated user organization."
            )
        self.ensure_organization_is_approved_for_write(announcement.organization)
        self.ensure_announcement_is_editable_for_write(announcement)
        payload_announcement = serializer.validated_data.get("announcement", announcement)
        if payload_announcement.uuid != announcement.uuid:
            raise ValidationError({"announcement": "Announcement must match the announcement in the URL."})
        serializer.save(announcement=announcement)

    def perform_update(self, serializer):
        announcement = self._get_announcement_from_url()
        if announcement.organization.user_id != self.request.user.id:
            raise PermissionDenied(
                "Announcement does not belong to the authenticated user organization."
            )
        self.ensure_organization_is_approved_for_write(announcement.organization)
        self.ensure_announcement_is_editable_for_write(announcement)
        payload_announcement = serializer.validated_data.get(
            "announcement",
            serializer.instance.announcement,
        )
        if payload_announcement.uuid != announcement.uuid:
            raise ValidationError({"announcement": "Announcement must match the announcement in the URL."})
        serializer.save(announcement=announcement)

    def perform_destroy(self, instance):
        self.ensure_organization_is_approved_for_write(instance.announcement.organization)
        self.ensure_announcement_is_editable_for_write(instance.announcement)
        super().perform_destroy(instance)


@extend_schema(tags=["Services"])
@extend_schema_view(
    list=extend_schema(
        tags=["Services"],
        summary="List service prices",
        description="Lists the service prices of the subservice specified in the URL.",
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter],
        auth=[],
    ),
    create=extend_schema(
        tags=["Services"],
        summary="Create service price",
        description="Creates a service price for the subservice specified in the URL.",
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter],
    ),
    retrieve=extend_schema(
        tags=["Services"],
        summary="Get service price",
        description="Returns a public service price belonging to the subservice specified in the URL.",
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter, service_price_uuid_parameter],
        auth=[],
    ),
    update=extend_schema(
        tags=["Services"],
        summary="Replace service price",
        description="Fully replaces a service price belonging to the subservice specified in the URL.",
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter, service_price_uuid_parameter],
    ),
    partial_update=extend_schema(
        tags=["Services"],
        summary="Update service price",
        description="Partially updates a service price belonging to the subservice specified in the URL.",
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter, service_price_uuid_parameter],
    ),
    destroy=extend_schema(
        tags=["Services"],
        summary="Delete service price",
        description="Deletes a service price belonging to the subservice specified in the URL.",
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter, service_price_uuid_parameter],
    ),
)
class ServicePriceViewSet(
    OrganizationVisibilityMixin,
    ActionScopedRateThrottleMixin,
    viewsets.ModelViewSet,
):
    serializer_class = ServicePriceSerializer
    queryset = ServicePrice.objects.select_related(
        "subservice",
        "subservice__announcement",
        "subservice__announcement__organization",
        "subservice__service_catalog",
    )
    lookup_field = "uuid"
    lookup_url_kwarg = "price_uuid"
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
        return [IsActiveAccount()]

    def get_queryset(self):
        queryset = self.queryset
        announcement_uuid = self.kwargs.get("announcement_uuid")
        if announcement_uuid is not None:
            if self.action in {"list", "retrieve"}:
                announcement = self._get_announcement_from_url()
                if not self.can_access_unapproved_organization(announcement.organization):
                    raise NotFound("Announcement not found.")
                queryset = queryset.filter(subservice__announcement=announcement)
            else:
                queryset = queryset.filter(
                    subservice__announcement__uuid=announcement_uuid,
                    subservice__announcement__organization__user=self.request.user,
                )
            queryset = queryset.filter(subservice__announcement__uuid=announcement_uuid)
        subservice_uuid = self.kwargs.get("subservice_uuid")
        if subservice_uuid is not None:
            if self.action in {"create", "update", "partial_update", "destroy"}:
                self._get_subservice_from_url()
            queryset = queryset.filter(subservice__uuid=subservice_uuid)
        return queryset

    def _get_announcement_from_url(self):
        announcement = Announcement.objects.select_related("organization").filter(
            uuid=self.kwargs["announcement_uuid"]
        ).first()
        if announcement is None:
            raise NotFound("Announcement not found.")
        return announcement

    def _get_subservice_from_url(self):
        announcement_uuid = self.kwargs.get("announcement_uuid")
        subservice_uuid = self.kwargs.get("subservice_uuid")
        subservice = Subservice.objects.select_related("announcement", "announcement__organization")
        subservice = subservice.filter(
            uuid=subservice_uuid,
            announcement__organization__user=self.request.user,
        )
        if announcement_uuid is not None:
            subservice = subservice.filter(announcement__uuid=announcement_uuid)
        subservice = subservice.first()
        if subservice is None:
            raise NotFound("Subservice not found.")
        return subservice

    def _get_subservice(self, serializer):
        subservice = self._get_subservice_from_url()
        if subservice.announcement.organization.user_id != self.request.user.id:
            raise PermissionDenied("Subservice does not belong to the authenticated user organization.")
        self.ensure_organization_is_approved_for_write(subservice.announcement.organization)
        self.ensure_announcement_is_editable_for_write(subservice.announcement)
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
        self.ensure_organization_is_approved_for_write(instance.subservice.announcement.organization)
        self.ensure_announcement_is_editable_for_write(instance.subservice.announcement)
        super().perform_destroy(instance)


@extend_schema(tags=["Services"])
@extend_schema_view(
    list=extend_schema(
        tags=["Services"],
        summary="List public service prices",
        description=(
            "Lists the public prices of a subservice identified by "
            "announcement UUID and subservice UUID."
        ),
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter],
        auth=[],
    ),
    retrieve=extend_schema(
        tags=["Services"],
        summary="Get public service price",
        description=(
            "Returns a public service price identified by announcement UUID, "
            "subservice UUID and price UUID."
        ),
        parameters=[announcement_nested_uuid_parameter, subservice_uuid_parameter, service_price_uuid_parameter],
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
        "subservice__announcement",
        "subservice__announcement__organization",
        "subservice__service_catalog",
    )
    lookup_field = "uuid"
    lookup_url_kwarg = "price_uuid"
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
        "retrieve": "organization_public_read",
    }

    def get_queryset(self):
        announcement = Announcement.objects.select_related("organization").filter(
            uuid=self.kwargs["announcement_uuid"]
        ).first()
        if announcement is None:
            raise NotFound("Announcement not found.")
        if not self.can_access_unapproved_organization(announcement.organization):
            raise NotFound("Announcement not found.")
        return self.queryset.filter(
            subservice__announcement=announcement,
            subservice__uuid=self.kwargs["subservice_uuid"],
        )
