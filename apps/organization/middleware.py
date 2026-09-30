from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.utils.crypto import salted_hmac

from common.client_ip import get_client_ip

from .models import Announcement


class AnnouncementViewCountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        resolver_match = getattr(request, "resolver_match", None)
        if (
            request.method == "GET"
            and response.status_code == 200
            and resolver_match is not None
            and resolver_match.url_name == "public-announcement-detail"
        ):
            announcement_uuid = resolver_match.kwargs.get("uuid")
            if announcement_uuid is not None:
                self._track_announcement_view(request)

        return response

    def _track_announcement_view(self, request):
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match is None:
            return

        announcement_uuid = resolver_match.kwargs.get("uuid")
        visitor_identifier = self._get_visitor_identifier(request)
        if announcement_uuid is None or visitor_identifier is None:
            return

        cache_key = f"organization:announcement-view:{announcement_uuid}:{visitor_identifier}"
        ttl = max(
            1,
            int(getattr(settings, "ORGANIZATION_ANNOUNCEMENT_VIEW_TTL_SECONDS", 60 * 60 * 24 * 30)),
        )
        if not cache.add(cache_key, True, timeout=ttl):
            return

        announcement_id = Announcement.objects.filter(uuid=announcement_uuid).values_list("id", flat=True).first()
        if announcement_id is None:
            return
        Announcement.objects.filter(pk=announcement_id).update(view_count=F("view_count") + 1)

        from apps.statistics.services import increment_announcement_view_stats

        increment_announcement_view_stats(announcement_id)

    def _get_visitor_identifier(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"user:{user.id}"

        # Anonymous API clients do not keep session cookies, and creating a
        # session row per request only bloated the table. De-duplicate on a
        # keyed hash of IP and user agent instead; it only lives in the cache.
        client_ip = get_client_ip(request)
        if client_ip is None:
            return None
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        digest = salted_hmac("announcement-view", f"{client_ip}|{user_agent}").hexdigest()
        return f"anon:{digest}"
