from django.urls import path

from .views import PublicAnnouncementViewSet

public_announcement_list = PublicAnnouncementViewSet.as_view({"get": "list"})

urlpatterns = [
    path(
        "",
        public_announcement_list,
        name="public-announcement-list",
    ),
]
