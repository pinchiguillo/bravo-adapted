from rest_framework.routers import DefaultRouter

from .views import RgpdAnonymousConsentViewSet, RgpdConsentViewSet, RgpdLegalDocumentViewSet

router = DefaultRouter()
router.register("legal-documents", RgpdLegalDocumentViewSet, basename="rgpd-legal-documents")
router.register("anonymous", RgpdAnonymousConsentViewSet, basename="rgpd-anonymous")
router.register("", RgpdConsentViewSet, basename="rgpd")

urlpatterns = router.urls
