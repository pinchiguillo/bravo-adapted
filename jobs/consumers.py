from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from .models import Job, JobChatMessage


class JobChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.job_uuid = self.scope["url_route"]["kwargs"]["job_uuid"]
        has_access = await self._user_has_job_access(self.job_uuid, user.id)
        if not has_access:
            await self.close(code=4403)
            return

        self.room_group_name = f"job_chat_{self.job_uuid}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message_text = str(content.get("content", "")).strip()
        if not message_text:
            await self.send_json({"detail": "Message content cannot be empty."})
            return

        if await self._is_rate_limited(self.scope["user"].id):
            await self.send_json({"detail": "Rate limit exceeded."})
            return

        message_payload = await self._save_message(self.job_uuid, self.scope["user"].id, message_text)
        if message_payload is None:
            await self.send_json({"detail": "You do not have access to this job."})
            await self.close(code=4403)
            return
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": message_payload,
            },
        )

    async def chat_message(self, event):
        await self.send_json(event["message"])

    @database_sync_to_async
    def _user_has_job_access(self, job_uuid, user_id):
        return Job.objects.filter(uuid=job_uuid).filter(
            Q(user_id=user_id) | Q(organization__user_id=user_id)
        ).exists()

    @database_sync_to_async
    def _is_rate_limited(self, user_id):
        limit = max(1, int(getattr(settings, "JOB_CHAT_WS_RATE_LIMIT", 20)))
        window = max(1, int(getattr(settings, "JOB_CHAT_WS_RATE_WINDOW", 60)))
        cache_key = f"jobs:chat-rate:{self.job_uuid}:{user_id}"

        if cache.add(cache_key, 1, timeout=window):
            return False

        try:
            current_value = cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=window)
            return False

        return current_value > limit

    @database_sync_to_async
    def _save_message(self, job_uuid, sender_id, content):
        job = (
            Job.objects.select_related("chat")
            .filter(uuid=job_uuid)
            .filter(Q(user_id=sender_id) | Q(organization__user_id=sender_id))
            .first()
        )
        if job is None:
            return None
        message = JobChatMessage.objects.create(chat=job.chat, sender_id=sender_id, content=content)
        return {
            "id": message.id,
            "uuid": str(message.uuid),
            "chat": message.chat_id,
            "sender": message.sender_id,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }
