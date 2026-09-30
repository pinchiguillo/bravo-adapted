from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.jobs.models import Job
from common.permissions import IsActiveAccount

from ..models import JobChatMessage
from ..serializers import JobChatAttachmentCreateSerializer, JobChatAttachmentSerializer


def _get_own_message(request, job_uuid, message_uuid):
    """Resolve the message a participant wants to attach a file to.

    Both the requester and the provider can attach files, but only to their
    own messages.
    """
    try:
        job = Job.objects.select_related("announcement__organization").get(uuid=job_uuid)
    except Job.DoesNotExist:
        raise NotFound("Job not found.")

    if not job.can_access_as_participant(request.user):
        raise PermissionDenied("You do not have permission to access this chat.")

    try:
        message = JobChatMessage.objects.get(uuid=message_uuid, job_chat__job=job)
    except JobChatMessage.DoesNotExist:
        raise NotFound("Message not found.")

    if message.user_id != request.user.id:
        raise PermissionDenied("You can only attach files to your own messages.")
    return message


@extend_schema(
    tags=["Job Chat"],
    summary="Attach asset to message",
    description=(
        "Attach a previously uploaded and confirmed Asset (kind=job_chat_attachment) "
        "to one of your own messages in a job chat. The asset must be in CONFIRMED "
        "status and owned by the authenticated user."
    ),
    request=JobChatAttachmentCreateSerializer,
    responses={
        status.HTTP_201_CREATED: JobChatAttachmentSerializer,
        status.HTTP_400_BAD_REQUEST: OpenApiResponse(description="Validation failed."),
        status.HTTP_404_NOT_FOUND: OpenApiResponse(description="Job or message not found."),
    },
)
@api_view(["POST"])
@permission_classes([IsActiveAccount])
def attach_to_message(request, job_uuid, message_uuid):
    """Attach a confirmed Asset to a chat message as an attachment."""
    message = _get_own_message(request, job_uuid, message_uuid)

    serializer = JobChatAttachmentCreateSerializer(
        data=request.data,
        context={"request": request, "message": message},
    )
    serializer.is_valid(raise_exception=True)
    attachment = serializer.save()

    return Response(JobChatAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)
