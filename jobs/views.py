import uuid

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError

from Core.throttling import ActionScopedRateThrottleMixin

from .models import Job
from .permissions import HasActiveJobAccess, IsJobMember
from .serializers import JobSerializer

job_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Search term with at least 3 characters to filter accessible jobs.",
)

job_category_parameter = OpenApiParameter(
    name="category",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Single category UUID filter kept for backwards compatibility.",
)

job_categories_parameter = OpenApiParameter(
    name="categories",
    type={"type": "array", "items": {"type": "string", "format": "uuid"}},
    location=OpenApiParameter.QUERY,
    required=False,
    explode=True,
    style="form",
    description="Optional list of category UUIDs used to filter accessible jobs.",
)


@extend_schema_view(
    list=extend_schema(
        summary="Search jobs",
        description=(
            "Lists the jobs where the authenticated user participates as a client or "
            "organization. Supports optional filtering by category UUIDs and plain text search."
        ),
        parameters=[job_categories_parameter, job_category_parameter, job_search_parameter],
    ),
    create=extend_schema(
        summary="Create job",
        description="Creates a new job associated with the authenticated user.",
    ),
    retrieve=extend_schema(
        summary="Get job",
        description="Returns the details of a job accessible to the authenticated user.",
    ),
    update=extend_schema(
        summary="Replace job",
        description="Fully replaces a job accessible to the authenticated user.",
    ),
    partial_update=extend_schema(
        summary="Update job",
        description="Partially updates a job accessible to the authenticated user.",
    ),
    destroy=extend_schema(
        summary="Delete job",
        description="Deletes a job accessible to the authenticated user.",
    ),
)
class JobViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Job.objects.select_related(
        "user",
        "announcement",
        "announcement__organization",
        "announcement__organization__user",
        "plan_price",
        "plan_price__subservice",
        "plan_price__subservice__service",
        "chat",
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "jobs"
    throttle_scope_action_map = {
        "list": "jobs_read",
        "retrieve": "jobs_read",
        "create": "jobs_write",
        "update": "jobs_write",
        "partial_update": "jobs_write",
        "destroy": "jobs_write",
    }

    def get_queryset(self):
        queryset = self.queryset
        if getattr(self.request.user, "is_staff", False):
            queryset = self.queryset
        else:
            user = self.request.user
            queryset = self.queryset.filter(
                Q(user=user) | Q(announcement__organization__user=user)
            ).distinct()

        if self.action == "list":
            queryset = self._filter_queryset(queryset)

        return queryset

    def get_permissions(self):
        if self.action == "destroy":
            return [HasActiveJobAccess(), permissions.IsAdminUser()]
        if self.action in {"retrieve", "update", "partial_update"}:
            return [HasActiveJobAccess(), IsJobMember()]
        return [HasActiveJobAccess()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def _filter_queryset(self, queryset):
        category_uuids = self._get_category_filters()
        if category_uuids:
            queryset = queryset.filter(announcement__category__uuid__in=category_uuids)

        search_query = self._get_search_query()
        if search_query:
            search_filter = (
                Q(status__icontains=search_query)
                | Q(user__email__icontains=search_query)
                | Q(user__username__icontains=search_query)
                | Q(announcement__name__icontains=search_query)
                | Q(announcement__organization__name__icontains=search_query)
                | Q(announcement__organization__legal_name__icontains=search_query)
            )
            search_uuid = self._parse_uuid(search_query)
            if search_uuid is not None:
                search_filter |= (
                    Q(uuid=search_uuid)
                    | Q(announcement__uuid=search_uuid)
                    | Q(announcement__organization__uuid=search_uuid)
                )
            queryset = queryset.filter(search_filter)

        return queryset.distinct()

    def _get_search_query(self):
        search_query = str(self.request.query_params.get("search", "")).strip()
        if not search_query:
            return ""
        if len(search_query) < 3:
            raise ValidationError(
                {"search": "Ensure this query parameter has at least 3 characters."}
            )
        return search_query

    def _get_category_filters(self):
        query_params = self.request.query_params
        if hasattr(query_params, "getlist"):
            raw_values = query_params.getlist("categories")
        else:
            raw_categories = query_params.get("categories", [])
            raw_values = raw_categories if isinstance(raw_categories, list) else [raw_categories]
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

    def _parse_uuid(self, raw_value):
        try:
            return uuid.UUID(raw_value)
        except (TypeError, ValueError, AttributeError):
            return None
