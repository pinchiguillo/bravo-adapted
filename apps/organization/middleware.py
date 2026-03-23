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
            and resolver_match.url_name == "organization-announcement-detail"
        ):
            announcement_uuid = resolver_match.kwargs.get("uuid")
            if announcement_uuid is not None:
                Announcement.objects.filter(uuid=announcement_uuid).update(
                    view_count=F("view_count") + 1
                )

        return response
