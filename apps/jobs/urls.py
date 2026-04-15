from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import JobViewSet, create_announcement_job

router = DefaultRouter()
router.register("", JobViewSet, basename="job")

urlpatterns = [
    path("announcements/<uuid:announcement_uuid>/jobs/", create_announcement_job, name="announcement-job-create"),
] + router.urls
