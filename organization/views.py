import uuid

from django.db.models import Q
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from Core.permissions import IsActiveAccount
from Core.throttling import ActionScopedRateThrottleMixin

from .models import (
    Announcement,
    Category,
    Organization,
    OrganizationJob,
    Service,
    ServicePrice,
    Subservice,
)
from .permissions import (
    IsAnnouncementOrganizationOwner,
    IsOrganizationOwner,
    IsServiceOrganizationOwner,
)
from .serializers import (
    AnnouncementSerializer,
    CategorySerializer,
    OrganizationJobSerializer,
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
    description="UUID of the organization that owns the nested resource.",
)

organization_job_uuid_parameter = OpenApiParameter(
    name="job_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the organization job that owns the service.",
)

announcement_uuid_parameter = OpenApiParameter(
    name="uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the announcement.",
)

service_uuid_parameter = OpenApiParameter(
    name="service_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the service that owns the nested subservice.",
)

organization_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Search term with at least 3 characters to filter organizations.",
)

announcement_category_parameter = OpenApiParameter(
    name="category",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Single category UUID filter kept for backwards compatibility.",
)

announcement_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional text used to filter announcements by their visible text fields.",
)

announcement_categories_parameter = OpenApiParameter(
    name="categories",
    type={"type": "array", "items": {"type": "string", "format": "uuid"}},
    location=OpenApiParameter.QUERY,
    required=False,
    explode=True,
    style="form",
    description="Optional list of category UUIDs used to filter announcements.",
)


class OrganizationSearchMixin:
    def filter_organizations_by_search(self, queryset):
        search_query = self.get_search_query()
        search_filter = (
            Q(name__icontains=search_query)
            | Q(legal_name__icontains=search_query)
            | Q(tax_id__icontains=search_query)
            | Q(billing_email__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(user__username__icontains=search_query)
        )
        search_uuid = self.parse_search_uuid(search_query)
        if search_uuid is not None:
            search_filter |= Q(uuid=search_uuid)
        return queryset.filter(search_filter).distinct()

    def get_search_query(self):
        search_query = str(self.request.query_params.get("search", "")).strip()
        if not search_query:
            raise ValidationError({"search": "This query parameter is required."})
        if len(search_query) < 3:
            raise ValidationError(
                {"search": "Ensure this query parameter has at least 3 characters."}
            )
        return search_query

    def parse_search_uuid(self, raw_value):
        try:
            return uuid.UUID(raw_value)
        except (TypeError, ValueError, AttributeError):
            return None


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


class UserOrganizationMixin:
    def get_user_organization(self):
        organization = (
            Organization.objects.select_related("user").with_rating().filter(user=self.request.user).first()
        )
        if organization is None:
            raise NotFound("Organization not found.")
        return organization


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


@extend_schema_view(
    list=extend_schema(
        summary="Get authenticated user organization",
        description="Returns the organization associated with the authenticated user.",
    ),
    create=extend_schema(
        summary="Create authenticated user organization",
        description="Creates an organization associated with the authenticated user.",
        request=OrganizationSerializer,
        responses={
            status.HTTP_201_CREATED: OrganizationSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Authenticated user already has an organization."
            ),
        },
    ),
    partial_update=extend_schema(
        summary="Update authenticated user organization",
        description="Partially updates the organization associated with the authenticated user.",
        request=OrganizationSerializer,
        responses={status.HTTP_200_OK: OrganizationSerializer},
    ),
)
class OrganizationUserViewSet(
    UserOrganizationMixin,
    ActionScopedRateThrottleMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationSerializer
    permission_classes = [IsActiveAccount]
    queryset = Organization.objects.select_related("user").with_rating()
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_authenticated_read",
        "create": "organization_write",
        "partial_update": "organization_write",
    }

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_user_organization())
        return Response(serializer.data, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        if Organization.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": "Authenticated user already has an organization."})
        serializer.save(user=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            self.get_user_organization(),
            data=request.data,
            partial=True,
        )
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


class AnnouncementPublicFilterMixin:
    public_search_fields = (
        "name",
        "location",
        "announcement",
        "description",
        "free_text",
        "organization__name",
        "category__name",
    )

    def filter_announcements(self, queryset):
        category_uuids = self._get_public_category_filters()
        search_query = str(self.request.query_params.get("search", "")).strip()

        if category_uuids:
            queryset = queryset.filter(category__uuid__in=category_uuids)
        if search_query:
            search_filter = Q()
            for field_name in self.public_search_fields:
                search_filter |= Q(**{f"{field_name}__icontains": search_query})
            queryset = queryset.filter(search_filter)
        return queryset.distinct()

    def _get_public_category_filters(self):
        raw_values = self.request.query_params.getlist("categories")
        if not raw_values:
            single_category = str(self.request.query_params.get("category", "")).strip()
            return [single_category] if single_category else []

        category_uuids = []
        for raw_value in raw_values:
            for part in str(raw_value).split(","):
                normalized_value = part.strip()
                if normalized_value:
                    category_uuids.append(normalized_value)
        return category_uuids


@extend_schema_view(
    list=extend_schema(
        summary="List public announcements",
        description=(
            "Lists active announcements. Supports optional filtering by category UUIDs "
            "and plain text search."
        ),
        parameters=[
            announcement_categories_parameter,
            announcement_category_parameter,
            announcement_search_parameter,
        ],
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
        Announcement.objects.select_related(
            "organization",
            "category",
        )
        .prefetch_related("services")
        .filter(status=Announcement.Status.ACTIVE)
    )
    throttle_scope_prefix = "organization"
    throttle_scope_action_map = {
        "list": "organization_public_read",
    }

    def get_queryset(self):
        return self.filter_announcements(self.queryset).order_by("-created_at", "-id")


@extend_schema_view(
    list=extend_schema(
        summary="List organization jobs",
        description="Lists the jobs of the organization specified in the URL.",
        parameters=[organization_uuid_parameter],
    ),
    create=extend_schema(
        summary="Create organization job",
        description=(
            "Creates an organization job in the organization specified in the URL "
            "if it belongs to the authenticated user."
        ),
        parameters=[organization_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get organization job",
        description="Returns the details of a job belonging to the organization specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace organization job",
        description="Fully replaces a job in the organization specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update organization job",
        description="Partially updates a job in the organization specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete organization job",
        description="Deletes a job in the organization specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter],
    ),
)
class OrganizationJobViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = OrganizationJobSerializer
    queryset = OrganizationJob.objects.select_related("organization")
    lookup_field = "uuid"
    lookup_url_kwarg = "job_uuid"
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

    def _validate_organization_owner(self, organization):
        if organization.user_id != self.request.user.id:
            raise PermissionDenied("Organization does not belong to the authenticated user.")

    def perform_create(self, serializer):
        organization = self._get_organization_from_url()
        self._validate_organization_owner(organization)
        serializer.save(organization=organization)

    def perform_update(self, serializer):
        organization = self._get_organization_from_url()
        self._validate_organization_owner(organization)
        serializer.save(organization=organization)

    def perform_destroy(self, instance):
        self._validate_organization_owner(instance.organization)
        instance.delete()


@extend_schema_view(
    list=extend_schema(
        summary="List services",
        description="Lists the services of the organization job specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter],
    ),
    create=extend_schema(
        summary="Create service",
        description=(
            "Creates a service in the organization job specified in the URL "
            "if it belongs to the authenticated user."
        ),
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get service",
        description="Returns the details of a service belonging to the organization job specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace service",
        description="Fully replaces a service in the organization job specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update service",
        description="Partially updates a service in the organization job specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete service",
        description="Deletes a service in the organization job specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
)
class ServiceViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    queryset = Service.objects.select_related("job", "job__organization")
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
            return [IsActiveAccount(), IsServiceOrganizationOwner()]
        return [IsActiveAccount()]

    def get_queryset(self):
        queryset = self.queryset
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is not None:
            queryset = queryset.filter(job__organization__uuid=organization_uuid)
        job_uuid = self.kwargs.get("job_uuid")
        if job_uuid is not None:
            queryset = queryset.filter(job__uuid=job_uuid)
        return queryset

    def _get_job_from_url(self):
        organization_uuid = self.kwargs.get("organization_uuid")
        job_uuid = self.kwargs.get("job_uuid")
        organization_job = OrganizationJob.objects.select_related("organization").filter(uuid=job_uuid)
        if organization_uuid is not None:
            organization_job = organization_job.filter(organization__uuid=organization_uuid)
        organization_job = organization_job.first()
        if organization_job is None:
            raise NotFound("Organization job not found.")
        return organization_job

    def perform_create(self, serializer):
        organization_job = self._get_job_from_url()
        if organization_job.organization.user_id != self.request.user.id:
            raise PermissionDenied("Organization does not belong to the authenticated user.")
        serializer.save(job=organization_job)


@extend_schema_view(
    list=extend_schema(
        summary="List announcements",
        description="Lists announcements for the organization specified in the URL.",
        parameters=[
            organization_uuid_parameter,
            announcement_categories_parameter,
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
class AnnouncementViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsActiveAccount]
    queryset = Announcement.objects.select_related(
        "organization",
        "category",
    ).prefetch_related("services")
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
            return [IsActiveAccount(), IsAnnouncementOrganizationOwner()]
        return [IsActiveAccount()]

    def get_queryset(self):
        queryset = self.queryset
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is not None:
            queryset = queryset.filter(organization__uuid=organization_uuid)
        category_uuids = self._get_category_filters()
        if category_uuids:
            queryset = queryset.filter(category__uuid__in=category_uuids)

        search_query = str(self.request.query_params.get("search", "")).strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(location__icontains=search_query)
                | Q(announcement__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(free_text__icontains=search_query)
            )

        return queryset.distinct()

    def _get_category_filters(self):
        raw_values = self.request.query_params.getlist("categories")
        category_uuids = []
        for raw_value in raw_values:
            for part in str(raw_value).split(","):
                normalized_value = part.strip()
                if normalized_value:
                    category_uuids.append(normalized_value)
        return category_uuids

    def get_serializer_context(self):
        context = super().get_serializer_context()
        organization_uuid = self.kwargs.get("organization_uuid")
        organization = Organization.objects.filter(uuid=organization_uuid).first()
        if organization is not None:
            context["organization"] = organization
        return context

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
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    create=extend_schema(
        summary="Create subservice",
        description="Creates a subservice associated with the service specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    retrieve=extend_schema(
        summary="Get subservice",
        description="Returns the details of a subservice belonging to the service specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace subservice",
        description="Fully replaces a subservice of the service specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update subservice",
        description="Partially updates a subservice of the service specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete subservice",
        description="Deletes a subservice of the service specified in the URL.",
        parameters=[organization_uuid_parameter, organization_job_uuid_parameter, service_uuid_parameter],
    ),
)
class SubserviceViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = SubserviceSerializer
    permission_classes = [IsActiveAccount]
    queryset = Subservice.objects.select_related(
        "service", "service__job", "service__job__organization"
    ).prefetch_related("price_table")
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
        queryset = self.queryset.filter(service__job__organization__user=self.request.user)
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is not None:
            queryset = queryset.filter(service__job__organization__uuid=organization_uuid)
        job_uuid = self.kwargs.get("job_uuid")
        if job_uuid is not None:
            queryset = queryset.filter(service__job__uuid=job_uuid)
        service_uuid = self.kwargs.get("service_uuid")
        if service_uuid is not None:
            queryset = queryset.filter(service__uuid=service_uuid)
        return queryset

    def _get_service_from_url(self):
        organization_uuid = self.kwargs.get("organization_uuid")
        job_uuid = self.kwargs.get("job_uuid")
        service_uuid = self.kwargs.get("service_uuid")
        service = Service.objects.select_related("job", "job__organization").filter(
            uuid=service_uuid
        )
        if organization_uuid is not None:
            service = service.filter(job__organization__uuid=organization_uuid)
        if job_uuid is not None:
            service = service.filter(job__uuid=job_uuid)
        service = service.first()
        if service is None:
            raise NotFound("Service not found.")
        return service

    def perform_create(self, serializer):
        service = self._get_service_from_url()
        if service.job.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        payload_service = serializer.validated_data["service"]
        if payload_service.uuid != service.uuid:
            raise ValidationError({"service": "Service must match the service in the URL."})
        serializer.save(service=service)

    def perform_update(self, serializer):
        service = self._get_service_from_url()
        if service.job.organization.user_id != self.request.user.id:
            raise PermissionDenied("Service does not belong to the authenticated user organization.")
        payload_service = serializer.validated_data.get("service", serializer.instance.service)
        if payload_service.uuid != service.uuid:
            raise ValidationError({"service": "Service must match the service in the URL."})
        serializer.save(service=service)


@extend_schema_view(
    list=extend_schema(
        summary="List service prices",
        description="Lists the service prices that belong to the authenticated organization owner.",
    ),
    create=extend_schema(
        summary="Create service price",
        description="Creates a service price for a subservice owned by the authenticated organization.",
    ),
    retrieve=extend_schema(
        summary="Get service price",
        description="Returns a service price owned by the authenticated organization.",
        parameters=[service_price_uuid_parameter],
    ),
    update=extend_schema(
        summary="Replace service price",
        description="Fully replaces a service price owned by the authenticated organization.",
        parameters=[service_price_uuid_parameter],
    ),
    partial_update=extend_schema(
        summary="Update service price",
        description="Partially updates a service price owned by the authenticated organization.",
        parameters=[service_price_uuid_parameter],
    ),
    destroy=extend_schema(
        summary="Delete service price",
        description="Deletes a service price owned by the authenticated organization.",
        parameters=[service_price_uuid_parameter],
    ),
)
class ServicePriceViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = ServicePriceSerializer
    permission_classes = [IsActiveAccount]
    queryset = ServicePrice.objects.select_related(
        "subservice",
        "subservice__service",
        "subservice__service__job",
        "subservice__service__job__organization",
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
        return self.queryset.filter(subservice__service__job__organization__user=self.request.user)

    def _get_subservice(self, serializer):
        subservice = serializer.validated_data.get("subservice", serializer.instance.subservice)
        if subservice.service.job.organization.user_id != self.request.user.id:
            raise PermissionDenied("Subservice does not belong to the authenticated user organization.")
        return subservice

    def perform_create(self, serializer):
        subservice = self._get_subservice(serializer)
        serializer.save(subservice=subservice)

    def perform_update(self, serializer):
        subservice = self._get_subservice(serializer)
        serializer.save(subservice=subservice)
