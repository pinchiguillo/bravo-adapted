import time

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache


async def allow_client_frame(user_id: int) -> bool:
    """Fixed-window rate limit for WebSocket frames, shared across workers via the cache.

    Counts per user rather than per socket, so opening more tabs does not
    raise the limit.
    """
    limit = settings.JOB_CHAT_WS_RATE_LIMIT
    window = settings.JOB_CHAT_WS_RATE_WINDOW
    key = f"job_chat_ws_rate:{user_id}:{int(time.time() // window)}"
    # Django's default async cache incr is a non-atomic get+set; the sync
    # incr maps to Redis INCR, so concurrent sockets cannot lose updates.
    if await sync_to_async(cache.add)(key, 1, timeout=window):
        return True
    try:
        count = await sync_to_async(cache.incr)(key)
    except ValueError:
        # The key expired between add() and incr(): this frame opens a new window.
        await sync_to_async(cache.add)(key, 1, timeout=window)
        return True
    return count <= limit
