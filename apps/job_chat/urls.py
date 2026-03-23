from rest_framework.routers import DefaultRouter

from .views import JobChatViewSet

router = DefaultRouter()
router.register("", JobChatViewSet, basename="job-chats")

urlpatterns = router.urls

