import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from apps.jobs.models import Job
from apps.notifications.services import emit_job_chat_message_notification
from common.exceptions import ConflictError, DomainError, NotFoundError, PermissionDeniedError

from .models import JobChat, JobChatMessage
from .serializers import (
    PROPOSAL_ACCEPTED,
    PROPOSAL_ANSWERS,
    PROPOSAL_PENDING,
    PROPOSAL_WIDGET,
    JobChatMessageSerializer,
)

logger = logging.getLogger(__name__)


def chat_group_name(job_uuid):
    return f"job_chat_{job_uuid}"


def post_message(*, job, user, message_type, content):
    """Persist a validated chat message, then notify the other participant.

    A failing notification must not lose or duplicate the message, so it is
    logged instead of propagated.
    """
    job_chat, _ = JobChat.objects.get_or_create(job=job)
    message = JobChatMessage.objects.create(job_chat=job_chat, user=user, type=message_type, content=content)
    try:
        emit_job_chat_message_notification(message)
    except Exception:
        logger.exception("Could not emit notification for chat message %s", message.uuid)
    return message


def set_proposal_status(*, job, message_uuid, actor, new_status):
    """Accept or reject a price proposal.

    Only the other participant can answer, and only while the proposal is
    pending. The row is locked so two concurrent answers cannot both win.
    """
    if new_status not in PROPOSAL_ANSWERS:
        raise DomainError("Status must be 'accepted' or 'rejected'.")

    with transaction.atomic():
        try:
            message = JobChatMessage.objects.select_for_update().get(uuid=message_uuid, job_chat__job=job)
        except (JobChatMessage.DoesNotExist, DjangoValidationError) as exc:
            raise NotFoundError("Message not found.") from exc

        if message.type != JobChatMessage.MessageType.WIDGET:
            raise DomainError("This message is not a widget.")
        try:
            widget = json.loads(message.content)
        except (TypeError, ValueError) as exc:
            raise DomainError("Invalid widget content.") from exc
        if not isinstance(widget, dict) or widget.get("widget_type") != PROPOSAL_WIDGET:
            raise DomainError("This widget is not a proposal.")
        proposal = widget.get("data")
        if not isinstance(proposal, dict):
            raise DomainError("Invalid widget content.")

        if message.user_id == actor.id:
            raise PermissionDeniedError("You cannot answer your own proposal.")
        if proposal.get("status", PROPOSAL_PENDING) != PROPOSAL_PENDING:
            raise ConflictError("This proposal has already been answered.")

        proposal["status"] = new_status
        message.content = json.dumps(widget)
        message.save(update_fields=["content", "updated_at"])

        if new_status == PROPOSAL_ACCEPTED:
            # Agreeing on a price is what starts the job.
            Job.objects.filter(pk=job.pk, status=Job.Status.PENDING).update(status=Job.Status.ACTIVE)
    return message


def broadcast_message(job_uuid, message):
    """Push a message to every socket connected to the job chat."""
    # Best effort: the message is already stored and clients can reload the
    # history, so a channel-layer outage must not turn the request into a 500.
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            chat_group_name(job_uuid),
            {"type": "chat_message", "message": JobChatMessageSerializer(message).data},
        )
    except Exception:
        logger.exception("Could not broadcast chat message %s", message.uuid)


def get_history_page(job_chat, *, before_uuid=None, limit=None):
    """Return (messages oldest-first, has_more) for the newest page before a message.

    Keyset pagination on (created_at, id): stable while new messages arrive,
    unlike offsets.
    """
    limit = limit or settings.JOB_CHAT_HISTORY_PAGE_SIZE
    messages = (
        job_chat.messages.select_related("user")
        .prefetch_related("attachments__asset")
        .order_by("-created_at", "-id")
    )
    if before_uuid:
        try:
            anchor = job_chat.messages.filter(uuid=before_uuid).values("created_at", "id").first()
        except DjangoValidationError as exc:
            raise NotFoundError("Message not found.") from exc
        if anchor is None:
            raise NotFoundError("Message not found.")
        messages = messages.filter(
            Q(created_at__lt=anchor["created_at"]) | Q(created_at=anchor["created_at"], id__lt=anchor["id"])
        )

    page = list(messages[: limit + 1])
    has_more = len(page) > limit
    return list(reversed(page[:limit])), has_more
