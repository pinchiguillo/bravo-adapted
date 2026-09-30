from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from common.exceptions import DomainError


def exception_handler(exc, context):
    """DRF exception handler that also understands service-layer DomainErrors."""
    if isinstance(exc, DomainError):
        return Response({"detail": exc.message, "code": exc.code}, status=exc.status_code)
    return drf_exception_handler(exc, context)
