from rest_framework.routers import DefaultRouter

from .views import (
    RgpdAnonymousConsentViewSet,
    RgpdConsentViewSet,
    RgpdDataRequestViewSet,
    RgpdLegalDocumentViewSet,
    RgpdPublicPolicyViewSet,
)

router = DefaultRouter()
router.register("documents", RgpdPublicPolicyViewSet, basename="rgpd-documents")
router.register("legal-documents", RgpdLegalDocumentViewSet, basename="rgpd-legal-documents")
router.register("requests", RgpdDataRequestViewSet, basename="rgpd-requests")
router.register("anonymous", RgpdAnonymousConsentViewSet, basename="rgpd-anonymous")
router.register("", RgpdConsentViewSet, basename="rgpd")

urlpatterns = router.urls
