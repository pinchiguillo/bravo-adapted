from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.jobs.models import Job
from common.permissions import IsActiveAccount

from ..models import JobChat
from ..serializers import (
    JobChatMessageCreateSerializer,
    JobChatMessageSerializer,
    JobChatSerializer,
    ProposalStatusUpdateSerializer,
)
from ..services import broadcast_message, post_message, set_proposal_status


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

    if not job.can_access_as_participant(request.user):
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

    if not job.can_access_as_participant(request.user):
        raise PermissionDenied("You don't have permission to send messages in this chat.")

    serializer = JobChatMessageCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    message = post_message(
        job=job,
        user=request.user,
        message_type=serializer.validated_data["type"],
        content=serializer.validated_data["content"],
    )
    broadcast_message(job.uuid, message)
    return Response(JobChatMessageSerializer(message).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Job Chat"],
    summary="Update proposal status",
    description="Accept or reject a pending proposal sent by the other participant.",
    request=ProposalStatusUpdateSerializer,
    responses={
        status.HTTP_200_OK: JobChatMessageSerializer,
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid message type or proposal structure."},
        status.HTTP_403_FORBIDDEN: {"description": "You don't have permission to update this message."},
        status.HTTP_404_NOT_FOUND: {"description": "Job or message not found."},
        status.HTTP_409_CONFLICT: {"description": "The proposal has already been answered."},
    },
)
@api_view(["PATCH"])
@permission_classes([IsActiveAccount])
def update_proposal_status(request, job_uuid, message_uuid):
    """Update the status of a proposal widget message (accept or reject)."""
    try:
        job = Job.objects.get(uuid=job_uuid)
    except Job.DoesNotExist:
        raise NotFound("Job not found.")

    if not job.can_access_as_participant(request.user):
        raise PermissionDenied("You don't have permission to update messages in this chat.")

    serializer = ProposalStatusUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    message = set_proposal_status(
        job=job,
        message_uuid=message_uuid,
        actor=request.user,
        new_status=serializer.validated_data["status"],
    )
    broadcast_message(job.uuid, message)
    return Response(JobChatMessageSerializer(message).data)
