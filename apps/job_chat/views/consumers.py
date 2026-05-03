import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.jobs.models import Job

from ..models import JobChat, JobChatMessage
from ..serializers import JobChatMessageSerializer, ProposalStatusUpdateSerializer

User = get_user_model()


class JobChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time job chat messaging."""

    async def connect(self):
        self.job_uuid = self.scope["url_route"]["kwargs"]["job_uuid"]
        self.job_chat_group = f"job_chat_{self.job_uuid}"
        self.user = self.scope["user"]

        # Check if user is authenticated
        if not self.user.is_authenticated:
            await self.close()
            return

        # Check permissions
        has_permission = await self.check_job_permission()
        if not has_permission:
            await self.close()
            return

        # Join room
        await self.channel_layer.group_add(self.job_chat_group, self.channel_name)
        await self.accept()

        # Notify others that user is online
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
        # Notify others that user is offline
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

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
            return

        message_type = data.get("type")

        if message_type == "history":
            await self.handle_history()
        elif message_type == "message":
            await self.handle_message(data)
        elif message_type == "proposal_status":
            await self.handle_proposal_status(data)
        elif message_type == "typing":
            await self.handle_typing(data)
        else:
            await self.send_error("Unknown message type")

    async def handle_history(self):
        """Send the full current chat history to the requesting socket."""
        history = await self.get_serialized_history()
        await self.send(
            text_data=json.dumps(
                {
                    "type": "history",
                    "data": history,
                }
            )
        )

    async def handle_message(self, data):
        """Handle incoming chat message."""
        content = data.get("content", "").strip()
        msg_type = data.get("msg_type", "plain_text")

        if not content:
            await self.send_error("Message content cannot be empty")
            return

        message = await self.save_message(content, msg_type)
        if message:
            await self.channel_layer.group_send(
                self.job_chat_group,
                {
                    "type": "chat_message",
                    "message": message,
                },
            )
            return

        await self.send_error("Message could not be saved")

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
        is_typing = data.get("is_typing", False)

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

    @database_sync_to_async
    def check_job_permission(self):
        """Check if user has permission to access this job chat."""
        try:
            job = Job.objects.get(uuid=self.job_uuid)
            return job.can_access_as_participant(self.user)
        except Job.DoesNotExist:
            return False

    @database_sync_to_async
    def get_serialized_history(self):
        """Load and serialize all persisted messages for this chat."""
        job = Job.objects.get(uuid=self.job_uuid)
        job_chat, _ = JobChat.objects.get_or_create(job=job)
        messages = job_chat.messages.select_related("user").prefetch_related("attachments__asset")
        return JobChatMessageSerializer(messages, many=True).data

    @database_sync_to_async
    def save_message(self, content, msg_type="plain_text"):
        """Save message to database."""
        try:
            job = Job.objects.get(uuid=self.job_uuid)
            job_chat, _ = JobChat.objects.get_or_create(job=job)

            message = JobChatMessage.objects.create(
                job_chat=job_chat,
                user=self.user,
                type=msg_type,
                content=content,
            )

            serializer = JobChatMessageSerializer(message)
            return serializer.data
        except Exception:
            return None

    @database_sync_to_async
    def update_proposal_status_message(self, message_uuid, status_value):
        """Update a proposal widget and return the serialized message."""
        try:
            serializer = ProposalStatusUpdateSerializer(data={"status": status_value})
            serializer.is_valid(raise_exception=True)

            job = Job.objects.get(uuid=self.job_uuid)
            job_chat, _ = JobChat.objects.get_or_create(job=job)
            message = job_chat.messages.get(uuid=message_uuid)

            if message.type != JobChatMessage.MessageType.WIDGET:
                raise serializers.ValidationError("This message is not a widget type.")

            try:
                widget_data = json.loads(message.content)
            except (json.JSONDecodeError, TypeError) as exc:
                raise serializers.ValidationError("Invalid widget content format.") from exc

            if widget_data.get("widget_type") != "proposal":
                raise serializers.ValidationError("This widget is not a proposal.")

            widget_data.setdefault("data", {})
            widget_data["data"]["status"] = serializer.validated_data["status"]
            message.content = json.dumps(widget_data)
            message.save(update_fields=["content", "updated_at"])

            return JobChatMessageSerializer(message).data, None
        except Job.DoesNotExist:
            return None, "Job not found."
        except JobChatMessage.DoesNotExist:
            return None, "Message not found."
        except serializers.ValidationError as exc:
            detail = exc.detail
            if isinstance(detail, list):
                return None, str(detail[0])
            if isinstance(detail, dict):
                first_value = next(iter(detail.values()))
                if isinstance(first_value, list):
                    return None, str(first_value[0])
                return None, str(first_value)
            return None, str(detail)
        except Exception:
            return None, "Message could not be updated"
