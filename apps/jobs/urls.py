from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import JobViewSet

router = DefaultRouter()
router.register("", JobViewSet, basename="job")

urlpatterns = [
    path("me/", JobViewSet.as_view({"get": "list"}), name="job-list-me"),
    *router.urls,
]
