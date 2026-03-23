from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from .models import Organization
from .serializers import OrganizationPublicSerializer


class OrganizationSearchConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.accept()
            await self.close(code=4401)
            return
        await self.accept()

    async def receive_json(self, content, **kwargs):
        query = str(content.get("q", "")).strip()
        if not query:
            await self.send_json(
                {
                    "type": "search.error",
                    "errors": {"q": "This field is required."},
                }
            )
            return

        if len(query) < 3:
            await self.send_json(
                {
                    "type": "search.error",
                    "errors": {"q": "Ensure this field has at least 3 characters."},
                }
            )
            return

        if await self._is_rate_limited(self.scope["user"].id):
            await self.send_json(
                {
                    "type": "search.error",
                    "errors": {"detail": "Rate limit exceeded."},
                }
            )
            return

        results = await self._search_organizations(query)
        await self.send_json(
            {
                "type": "search.results",
                "query": query,
                "results": results,
            }
        )

    @database_sync_to_async
    def _search_organizations(self, query):
        result_limit = max(1, int(getattr(settings, "ORGANIZATION_SEARCH_WS_RESULT_LIMIT", 10)))
        queryset = (
            Organization.objects
            .with_rating()
            .filter(
                Q(name__icontains=query)
                | Q(legal_name__icontains=query)
            )
            .order_by("name")
        )[:result_limit]
        return OrganizationPublicSerializer(queryset, many=True).data

    @database_sync_to_async
    def _is_rate_limited(self, user_id):
        limit = max(1, int(getattr(settings, "ORGANIZATION_SEARCH_WS_RATE_LIMIT", 20)))
        window = max(1, int(getattr(settings, "ORGANIZATION_SEARCH_WS_RATE_WINDOW", 60)))
        cache_key = f"organization:search-rate:{user_id}"

        if cache.add(cache_key, 1, timeout=window):
            return False

        try:
            current_value = cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=window)
            return False

        return current_value > limit
