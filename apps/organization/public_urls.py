from django.urls import path

from .views import PublicAnnouncementDetailViewSet, PublicAnnouncementViewSet

public_announcement_list = PublicAnnouncementViewSet.as_view({"get": "list"})
public_announcement_detail = PublicAnnouncementDetailViewSet.as_view({"get": "retrieve"})

urlpatterns = [
    path(
        "",
        public_announcement_list,
        name="public-announcement-list",
    ),
    path(
        "<uuid:organization_uuid>/<uuid:uuid>/",
        public_announcement_detail,
        name="public-announcement-detail",
    ),
]
