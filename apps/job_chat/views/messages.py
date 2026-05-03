import json

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.jobs.models import Job
from common.permissions import IsActiveAccount

from ..models import JobChat, JobChatMessage
from ..serializers import (
    JobChatMessageCreateSerializer,
    JobChatMessageSerializer,
    JobChatSerializer,
    ProposalStatusUpdateSerializer,
)


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

    job_chat, _ = JobChat.objects.get_or_create(job=job)

    serializer = JobChatMessageCreateSerializer(data=request.data)
    if serializer.is_valid():
        message = job_chat.messages.create(
            user=request.user,
            type=serializer.validated_data.get("type", JobChatMessage.MessageType.PLAIN_TEXT),
            content=serializer.validated_data["content"],
        )
        output_serializer = JobChatMessageSerializer(message)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Job Chat"],
    summary="Update proposal status",
    description="Accept or reject a proposal widget message. Only for widget-type messages with proposal type.",
    request=ProposalStatusUpdateSerializer,
    responses={
        status.HTTP_200_OK: JobChatMessageSerializer,
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid message type or proposal structure."},
        status.HTTP_403_FORBIDDEN: {"description": "You don't have permission to update this message."},
        status.HTTP_404_NOT_FOUND: {"description": "Job or message not found."},
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

    try:
        job_chat = JobChat.objects.get(job=job)
        message = job_chat.messages.get(uuid=message_uuid)
    except (JobChat.DoesNotExist, JobChatMessage.DoesNotExist):
        raise NotFound("Message not found.")

    # Validate message type
    if message.type != JobChatMessage.MessageType.WIDGET:
        raise ValidationError("This message is not a widget type.")

    # Parse and validate widget content
    try:
        widget_data = json.loads(message.content)
    except (json.JSONDecodeError, TypeError):
        raise ValidationError("Invalid widget content format.")

    if widget_data.get("widget_type") != "proposal":
        raise ValidationError("This widget is not a proposal.")

    # Validate request
    serializer = ProposalStatusUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Update proposal status
    new_status = serializer.validated_data["status"]
    widget_data["data"]["status"] = new_status
    message.content = json.dumps(widget_data)
    message.save(update_fields=["content"])

    # Return updated message
    output_serializer = JobChatMessageSerializer(message)
    return Response(output_serializer.data)
