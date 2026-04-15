from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied

from common.permissions import IsActiveAccount

from .models import Job
from .serializers import JobCreateSerializer, JobSerializer, JobUpdateSerializer


@extend_schema(tags=["Jobs"])
@extend_schema_view(
    list=extend_schema(
        summary="List jobs",
        description="Returns a paginated list of jobs for the authenticated user.",
    ),
    create=extend_schema(
        summary="Create job",
        description="Creates a new job associated with the authenticated user.",
        request=JobCreateSerializer,
        responses={
            status.HTTP_201_CREATED: JobSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(description="Invalid data provided."),
        },
    ),
    retrieve=extend_schema(
        summary="Get job details",
        description="Returns the details of a specific job by UUID.",
    ),
    update=extend_schema(
        summary="Update job",
        description="Updates a job's status or rating.",
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
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = JobSerializer
    queryset = Job.objects.select_related("user", "announcement", "plan_price").order_by("-created_at")
    lookup_field = "uuid"
    permission_classes = [IsActiveAccount]

    def get_queryset(self):
        if self.action == "list":
            return super().get_queryset().filter(user=self.request.user)
        return super().get_queryset()

    def get_serializer_class(self):
        if self.action == "create":
            return JobCreateSerializer
        if self.action in ("update", "partial_update"):
            return JobUpdateSerializer
        return JobSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        job = self.get_object()
        if job.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied("You don't have permission to update this job.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied("You don't have permission to delete this job.")
        instance.delete()

    def get_object(self):
        obj = super().get_object()
        if self.action not in ("list",):
            if obj.user != self.request.user and not self.request.user.is_staff:
                raise NotFound("Job not found.")
        return obj
