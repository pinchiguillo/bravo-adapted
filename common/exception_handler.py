from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from common.exceptions import DomainError


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler that also understands service-layer DomainErrors."""
    if isinstance(exc, DomainError):
        body = {exc.field: exc.message} if exc.field else {"detail": exc.message, "code": exc.code}
        return Response(body, status=exc.status_code)
    return drf_exception_handler(exc, context)
