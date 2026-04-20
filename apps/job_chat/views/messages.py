from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.jobs.models import Job
from common.permissions import IsActiveAccount

from ..models import JobChat
from ..serializers import JobChatMessageCreateSerializer, JobChatMessageSerializer, JobChatSerializer


@extend_schema(
    tags=["Job Chat"],
    summary="Get job chat messages",
    description="Retrieve all messages for a job chat. Requires being the job owner or staff.",
    responses={
        status.HTTP_200_OK: JobChatSerializer,
        status.HTTP_403_FORBIDDEN: {"description": "You don't have permission to access this chat."},
        status.HTTP_404_NOT_FOUND: {"description": "Job or chat not found."},
    },
)
@api_view(["GET"])
@permission_classes([IsActiveAccount])
def get_job_chat_messages(request, job_uuid):
    """Get all messages for a job chat."""
    try:
        job = Job.objects.get(uuid=job_uuid)
    except Job.DoesNotExist:
        raise NotFound("Job not found.")

    # Check permissions
    if job.user != request.user and not request.user.is_staff:
        raise PermissionDenied("You don't have permission to access this chat.")

    job_chat, _ = JobChat.objects.get_or_create(job=job)
    serializer = JobChatSerializer(job_chat)
    return Response(serializer.data)


@extend_schema(
    tags=["Job Chat"],
    summary="Send a message",
    description="Send a message to a job chat. Requires being the job owner or staff.",
    request=JobChatMessageCreateSerializer,
    responses={
        status.HTTP_201_CREATED: JobChatMessageSerializer,
        status.HTTP_403_FORBIDDEN: {"description": "You don't have permission to send messages in this chat."},
        status.HTTP_404_NOT_FOUND: {"description": "Job or chat not found."},
    },
)
@api_view(["POST"])
@permission_classes([IsActiveAccount])
def send_job_chat_message(request, job_uuid):
    """Send a message to a job chat."""
    try:
        job = Job.objects.get(uuid=job_uuid)
    except Job.DoesNotExist:
        raise NotFound("Job not found.")

    # Check permissions
    if job.user != request.user and not request.user.is_staff:
        raise PermissionDenied("You don't have permission to send messages in this chat.")

    job_chat, _ = JobChat.objects.get_or_create(job=job)

    serializer = JobChatMessageCreateSerializer(data=request.data)
    if serializer.is_valid():
        message = job_chat.messages.create(
            user=request.user,
            content=serializer.validated_data["content"],
        )
        output_serializer = JobChatMessageSerializer(message)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
