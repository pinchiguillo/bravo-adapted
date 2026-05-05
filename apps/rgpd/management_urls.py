from rest_framework.routers import DefaultRouter

from .views import (
    ManagementRgpdDataRequestViewSet,
    ManagementRgpdPolicyDocumentViewSet,
    ManagementRgpdPolicyVersionViewSet,
)

router = DefaultRouter()
router.register("documents", ManagementRgpdPolicyDocumentViewSet, basename="management-rgpd-documents")
router.register("document-versions", ManagementRgpdPolicyVersionViewSet, basename="management-rgpd-document-versions")
router.register("requests", ManagementRgpdDataRequestViewSet, basename="management-rgpd-requests")

urlpatterns = router.urls
