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


@extend_schema_view(
    list=extend_schema(
        summary="Search jobs",
        description="Searches the jobs where the authenticated user participates as a client or organization.",
        parameters=[job_search_parameter],
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
        "organization",
        "organization__user",
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
            queryset = self.queryset.filter(Q(user=user) | Q(organization__user=user)).distinct()

        if self.action == "list":
            queryset = self._filter_queryset_by_search(queryset)

        return queryset

    def get_permissions(self):
        if self.action == "destroy":
            return [HasActiveJobAccess(), permissions.IsAdminUser()]
        if self.action in {"retrieve", "update", "partial_update"}:
            return [HasActiveJobAccess(), IsJobMember()]
        return [HasActiveJobAccess()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def _filter_queryset_by_search(self, queryset):
        search_query = self._get_search_query()
        search_filter = (
            Q(status__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(organization__name__icontains=search_query)
            | Q(organization__legal_name__icontains=search_query)
        )
        search_uuid = self._parse_uuid(search_query)
        if search_uuid is not None:
            search_filter |= Q(uuid=search_uuid) | Q(organization__uuid=search_uuid)
        return queryset.filter(search_filter).distinct()

    def _get_search_query(self):
        search_query = str(self.request.query_params.get("search", "")).strip()
        if not search_query:
            raise ValidationError({"search": "This query parameter is required."})
        if len(search_query) < 3:
            raise ValidationError(
                {"search": "Ensure this query parameter has at least 3 characters."}
            )
        return search_query

    def _parse_uuid(self, raw_value):
        try:
            return uuid.UUID(raw_value)
        except (TypeError, ValueError, AttributeError):
            return None
