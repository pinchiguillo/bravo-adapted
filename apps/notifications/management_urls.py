from rest_framework.routers import DefaultRouter

from .views import ManagementNotificationTemplateViewSet, ManagementNotificationViewSet

router = DefaultRouter()
router.register("templates", ManagementNotificationTemplateViewSet, basename="management-notification-templates")
router.register("", ManagementNotificationViewSet, basename="management-notifications")

urlpatterns = router.urls
