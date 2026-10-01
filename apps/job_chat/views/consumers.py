import json
import logging
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from apps.jobs.models import Job
from common.exceptions import DomainError
from common.permissions import user_can_authenticate

from ..models import JobChat
from ..rate_limit import allow_client_frame
from ..serializers import JobChatMessageCreateSerializer, JobChatMessageSerializer, ProposalStatusUpdateSerializer
from ..services import chat_group_name, get_history_page, post_message, set_proposal_status

logger = logging.getLogger(__name__)

# Close code for sockets whose token expired or whose access was revoked.
CLOSE_SESSION_INVALID = 4401
# Identical typing indicators within this many seconds are not re-broadcast.
TYPING_REPEAT_SECONDS = 2


def first_error(errors):
    """Return the first human-readable message from DRF serializer errors."""
    while isinstance(errors, dict | list) and errors:
        errors = next(iter(errors.values())) if isinstance(errors, dict) else errors[0]
    return str(errors)


class JobChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time job chat messaging."""

    async def connect(self):
        self.job_uuid = self.scope["url_route"]["kwargs"]["job_uuid"]
        self.job_chat_group = chat_group_name(self.job_uuid)
        self.user = self.scope["user"]
        self.joined = False

        if not self.user.is_authenticated:
            await self.close()
            return

        if not await self.check_job_permission():
            await self.close()
            return

        await self.channel_layer.group_add(self.job_chat_group, self.channel_name)
        self.joined = True
        # Echo the auth subprotocol back, or browsers that offered one drop the connection.
        await self.accept(subprotocol=self.scope.get("auth_subprotocol"))

        await self.channel_layer.group_send(
            self.job_chat_group,
            {
                "type": "user_status_update",
                "status": "online",
                "user_id": self.user.id,
                "username": self.user.username,
            },
        )

    async def disconnect(self, close_code):
        # Channels calls disconnect() for rejected sockets too; they never joined
        # the room and must not broadcast presence into it.
        if not getattr(self, "joined", False):
            return

        await self.channel_layer.group_send(
            self.job_chat_group,
            {
                "type": "user_status_update",
                "status": "offline",
                "user_id": self.user.id,
                "username": self.user.username,
            },
        )
        await self.channel_layer.group_discard(self.job_chat_group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            await self.send_error("Binary frames are not supported")
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
            return
        if not isinstance(data, dict):
            await self.send_error("Messages must be JSON objects")
            return

        if data.get("type") != "typing":
            if not await allow_client_frame(self.user.id):
                await self.send_error("Rate limit exceeded, slow down")
                return
            # A socket outlives the checks made at connect time: re-validate the
            # token expiry, the account and the participation before acting.
            if self.token_expired() or not await self.still_allowed():
                await self.send_error("Session is no longer valid")
                await self.close(code=CLOSE_SESSION_INVALID)
                return

        try:
            await self.dispatch_client_message(data)
        except Exception:
            logger.exception("Unhandled error in job chat %s", self.job_uuid)
            await self.send_error("Internal error")

    async def dispatch_client_message(self, data):
        message_type = data.get("type")

        if message_type == "history":
            await self.handle_history(data)
        elif message_type == "message":
            await self.handle_message(data)
        elif message_type == "proposal_status":
            await self.handle_proposal_status(data)
        elif message_type == "typing":
            await self.handle_typing(data)
        else:
            await self.send_error("Unknown message type")

    async def handle_history(self, data):
        """Send one page of history (oldest first) to the requesting socket."""
        try:
            history, has_more = await self.get_serialized_history(data.get("before"))
        except DomainError as exc:
            await self.send_error(exc.message)
            return
        await self.send(
            text_data=json.dumps(
                {
                    "type": "history",
                    "data": history,
                    "has_more": has_more,
                }
            )
        )

    async def handle_message(self, data):
        """Validate and persist a chat message, then broadcast it to the room."""
        serializer = JobChatMessageCreateSerializer(
            data={"type": data.get("msg_type", "plain_text"), "content": data.get("content")}
        )
        if not serializer.is_valid():
            await self.send_error(first_error(serializer.errors))
            return

        message = await self.save_message(
            serializer.validated_data["type"],
            serializer.validated_data["content"],
        )
        await self.channel_layer.group_send(
            self.job_chat_group,
            {
                "type": "chat_message",
                "message": message,
            },
        )

    async def handle_proposal_status(self, data):
        """Handle proposal widget status changes over WebSocket."""
        message_uuid = data.get("message_uuid")
        status_value = data.get("status")

        if not message_uuid:
            await self.send_error("message_uuid is required")
            return

        if not status_value:
            await self.send_error("status is required")
            return

        updated_message, error = await self.update_proposal_status_message(
            message_uuid,
            status_value,
        )
        if error:
            await self.send_error(error)
            return

        await self.channel_layer.group_send(
            self.job_chat_group,
            {
                "type": "chat_message",
                "message": updated_message,
            },
        )

    async def handle_typing(self, data):
        """Handle typing status."""
        is_typing = data.get("is_typing") is True
        now = time.monotonic()
        last_state, last_sent = getattr(self, "last_typing", (None, 0.0))
        if is_typing == last_state and now - last_sent < TYPING_REPEAT_SECONDS:
            return
        self.last_typing = (is_typing, now)

        await self.channel_layer.group_send(
            self.job_chat_group,
            {
                "type": "typing_status",
                "user_id": self.user.id,
                "username": self.user.username,
                "is_typing": is_typing,
            },
        )

    async def chat_message(self, event):
        """Broadcast chat message to WebSocket."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "data": event["message"],
                }
            )
        )

    async def user_status_update(self, event):
        """Broadcast user status update."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_status",
                    "status": event["status"],
                    "user_id": event["user_id"],
                    "username": event["username"],
                }
            )
        )

    async def typing_status(self, event):
        """Broadcast typing status."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "typing",
                    "user_id": event["user_id"],
                    "username": event["username"],
                    "is_typing": event["is_typing"],
                }
            )
        )

    async def send_error(self, message):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "message": message,
                }
            )
        )

    def token_expired(self):
        expires_at = self.scope.get("auth_expires_at")
        return expires_at is not None and time.time() >= expires_at

    @database_sync_to_async
    def still_allowed(self):
        """Re-check that the account is active and still a participant of the job."""
        user = get_user_model().objects.filter(pk=self.user.pk).first()
        if user is None or not user_can_authenticate(user):
            return False
        job = Job.objects.select_related("announcement__organization").filter(uuid=self.job_uuid).first()
        return job is not None and job.can_access_as_participant(user)

    @database_sync_to_async
    def check_job_permission(self):
        """Check if user has permission to access this job chat."""
        try:
            job = Job.objects.get(uuid=self.job_uuid)
            return job.can_access_as_participant(self.user)
        except Job.DoesNotExist:
            return False

    @database_sync_to_async
    def get_serialized_history(self, before_uuid=None):
        job = Job.objects.get(uuid=self.job_uuid)
        job_chat, _ = JobChat.objects.get_or_create(job=job)
        messages, has_more = get_history_page(job_chat, before_uuid=before_uuid)
        return JobChatMessageSerializer(messages, many=True).data, has_more

    @database_sync_to_async
    def save_message(self, message_type, content):
        job = Job.objects.get(uuid=self.job_uuid)
        message = post_message(job=job, user=self.user, message_type=message_type, content=content)
        return JobChatMessageSerializer(message).data

    @database_sync_to_async
    def update_proposal_status_message(self, message_uuid, status_value):
        """Answer a proposal; returns (serialized message, None) or (None, error message)."""
        serializer = ProposalStatusUpdateSerializer(data={"status": status_value})
        if not serializer.is_valid():
            return None, first_error(serializer.errors)
        try:
            job = Job.objects.get(uuid=self.job_uuid)
            message = set_proposal_status(
                job=job,
                message_uuid=message_uuid,
                actor=self.user,
                new_status=serializer.validated_data["status"],
            )
        except Job.DoesNotExist:
            return None, "Job not found."
        except DomainError as exc:
            return None, exc.message
        return JobChatMessageSerializer(message).data, None
