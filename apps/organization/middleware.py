from django.conf import settings
from django.core.cache import cache
from django.db.models import F

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
        if cache.add(cache_key, True, timeout=ttl):
            Announcement.objects.filter(uuid=announcement_uuid).update(view_count=F("view_count") + 1)

    def _get_visitor_identifier(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"user:{user.id}"

        session = getattr(request, "session", None)
        if session is None:
            return None

        session_key = session.session_key
        if not session_key:
            session.save()
            session_key = session.session_key
        if not session_key:
            return None
        return f"anon:{session_key}"
