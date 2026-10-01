from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.job_chat.models import JobChatMessage
from common.permissions import IsActiveAccount

from ..models import Job
from ..serializers import JobListSerializer, JobSerializer, JobUpdateSerializer


@extend_schema(tags=["Jobs"])
@extend_schema_view(
    list=extend_schema(
        summary="List my jobs",
        description=(
            "Returns jobs for the current user with chat metadata. "
            "Use role=user to list jobs as requester or role=provider/organization "
            "to list jobs for announcements owned by the authenticated provider."
        ),
        parameters=[
            OpenApiParameter(
                name="role",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Participant role filter: user, provider, or organization.",
            )
        ],
        responses={status.HTTP_200_OK: JobListSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Get job details",
        description="Returns the details of a specific job by UUID.",
    ),
    update=extend_schema(
        summary="Update job",
        description="Moves a job through the participant's allowed transitions; the requester rates completed jobs.",
        request=JobUpdateSerializer,
        responses={
            status.HTTP_200_OK: JobSerializer,
            status.HTTP_403_FORBIDDEN: OpenApiResponse(description="You don't have permission to update this job."),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(description="Job not found."),
        },
    ),
    partial_update=extend_schema(
        summary="Partially update job",
        description="Partially updates a job's status or rating.",
        request=JobUpdateSerializer,
        responses={
            status.HTTP_200_OK: JobSerializer,
            status.HTTP_403_FORBIDDEN: OpenApiResponse(description="You don't have permission to update this job."),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(description="Job not found."),
        },
    ),
    destroy=extend_schema(
        summary="Delete job",
        description="Deletes a job.",
        responses={
            status.HTTP_204_NO_CONTENT: OpenApiResponse(description="Job deleted successfully."),
            status.HTTP_403_FORBIDDEN: OpenApiResponse(description="You don't have permission to delete this job."),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(description="Job not found."),
        },
    ),
)
class JobViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    ROLE_USER = "user"
    ROLE_PROVIDER = "provider"
    ROLE_ORGANIZATION = "organization"

    serializer_class = JobSerializer
    queryset = Job.objects.select_related("user", "announcement", "plan_price").order_by("-created_at")
    lookup_field = "uuid"
    permission_classes = [IsActiveAccount]

    def get_serializer_class(self):
        if self.action == "list":
            return JobListSerializer
        if self.action in ("update", "partial_update"):
            return JobUpdateSerializer
        return JobSerializer

    def get_queryset(self):
        base_queryset = super().get_queryset()

        if self.action == "list":
            role = self._get_list_role()
            if role == self.ROLE_PROVIDER:
                base_queryset = base_queryset.filter(announcement__organization__user=self.request.user)
            else:
                base_queryset = base_queryset.filter(user=self.request.user)
            latest_message = JobChatMessage.objects.filter(job_chat__job=OuterRef("pk")).order_by("-created_at", "-id")
            return base_queryset.select_related(
                "user",
                "announcement",
                "announcement__organization",
                "announcement__category",
                "plan_price",
            ).annotate(
                last_message_at=Subquery(latest_message.values("created_at")[:1]),
                last_message_type=Subquery(latest_message.values("type")[:1]),
                last_message_content=Subquery(latest_message.values("content")[:1]),
            )

        return base_queryset

    def _get_list_role(self):
        role = self.request.query_params.get("role", self.ROLE_USER).strip().lower()
        if role == self.ROLE_ORGANIZATION:
            return self.ROLE_PROVIDER
        if role not in {self.ROLE_USER, self.ROLE_PROVIDER}:
            raise ValidationError({"role": "Invalid role. Expected 'user', 'provider', or 'organization'."})
        return role

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_update(self, serializer):
        job = serializer.instance
        user = self.request.user
        if not (job.is_requester(user) or job.is_provider(user) or user.is_staff):
            raise PermissionDenied("You don't have permission to update this job.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied("You don't have permission to delete this job.")
        # Once a job is under way its chat holds the agreed proposal; keep it.
        if instance.status != Job.Status.PENDING and not self.request.user.is_staff:
            raise ValidationError({"status": "Only pending jobs can be deleted; move the job to inactive instead."})
        instance.delete()

    def get_object(self):
        obj = super().get_object()
        if not obj.can_access_as_participant(self.request.user):
            raise NotFound("Job not found.")
        return obj
