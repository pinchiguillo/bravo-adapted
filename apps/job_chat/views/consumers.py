import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from apps.jobs.models import Job

from ..models import JobChat, JobChatMessage
from ..serializers import JobChatMessageSerializer

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
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": "Invalid JSON format"}
                )
            )
            return

        message_type = data.get("type")

        if message_type == "message":
            await self.handle_message(data)
        elif message_type == "typing":
            await self.handle_typing(data)
        else:
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": "Unknown message type"}
                )
            )

    async def handle_message(self, data):
        """Handle incoming chat message."""
        content = data.get("content", "").strip()

        if not content:
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": "Message content cannot be empty"}
                )
            )
            return

        message = await self.save_message(content)
        if message:
            await self.channel_layer.group_send(
                self.job_chat_group,
                {
                    "type": "chat_message",
                    "message": message,
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

    @database_sync_to_async
    def check_job_permission(self):
        """Check if user has permission to access this job chat."""
        try:
            job = Job.objects.get(uuid=self.job_uuid)
            return job.user == self.user or self.user.is_staff
        except Job.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, content):
        """Save message to database."""
        try:
            job = Job.objects.get(uuid=self.job_uuid)
            job_chat, _ = JobChat.objects.get_or_create(job=job)

            message = JobChatMessage.objects.create(
                job_chat=job_chat,
                user=self.user,
                content=content,
            )

            serializer = JobChatMessageSerializer(message)
            return serializer.data
        except Exception:
            return None
