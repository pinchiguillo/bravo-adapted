import time

from django.conf import settings
from django.core.cache import cache


async def allow_client_frame(user_id):
    """Fixed-window rate limit for WebSocket frames, shared across workers via the cache.

    Counts per user rather than per socket, so opening more tabs does not
    raise the limit.
    """
    limit = settings.JOB_CHAT_WS_RATE_LIMIT
    window = settings.JOB_CHAT_WS_RATE_WINDOW
    key = f"job_chat_ws_rate:{user_id}:{int(time.time() // window)}"
    if await cache.aadd(key, 1, timeout=window):
        return True
    try:
        count = await cache.aincr(key)
    except ValueError:
        # The key expired between add() and incr(): this frame opens a new window.
        await cache.aadd(key, 1, timeout=window)
        return True
    return count <= limit
