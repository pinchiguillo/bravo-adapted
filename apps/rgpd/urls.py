from rest_framework.routers import DefaultRouter

from .views import RgpdAnonymousConsentViewSet, RgpdConsentViewSet

router = DefaultRouter()
router.register("anonymous", RgpdAnonymousConsentViewSet, basename="rgpd-anonymous")
router.register("", RgpdConsentViewSet, basename="rgpd")

urlpatterns = router.urls
