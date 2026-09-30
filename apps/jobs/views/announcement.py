from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.organization.models import Announcement
from common.permissions import IsActiveAccount

from ..models import Job
from ..serializers import JobCreateSerializer, JobSerializer


@extend_schema(
    tags=["Jobs"],
    summary="Create job for announcement",
    description="Creates a new job associated with the authenticated user for a specific announcement.",
    request=JobCreateSerializer,
    responses={
        status.HTTP_201_CREATED: JobSerializer,
        status.HTTP_400_BAD_REQUEST: OpenApiResponse(description="Invalid data provided."),
        status.HTTP_404_NOT_FOUND: OpenApiResponse(description="Announcement not found."),
    },
)
@api_view(["POST"])
@permission_classes([IsActiveAccount])
def create_announcement_job(request, announcement_uuid):
    """Create a job for a specific announcement."""
    try:
        announcement = Announcement.objects.select_related("organization").get(uuid=announcement_uuid)
    except Announcement.DoesNotExist:
        raise NotFound("Announcement not found.")

    serializer = JobCreateSerializer(
        data=request.data,
        context={"request": request, "announcement": announcement},
    )
    serializer.is_valid(raise_exception=True)
    job = Job.objects.create(
        user=request.user,
        announcement=announcement,
        plan_price=serializer.validated_data.get("plan_price"),
        status=Job.Status.PENDING,
    )
    return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)
