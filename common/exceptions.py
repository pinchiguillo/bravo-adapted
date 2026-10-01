"""Business-rule errors raised by the service layer.

Services stay independent of HTTP: they raise these, and the API layer maps
them to responses (see common.exception_handler) or, for WebSockets, to
error frames.
"""


class DomainError(Exception):
    status_code = 400
    default_code = "invalid"

    def __init__(self, message: str, *, code: str | None = None, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        # When set, the API reports the error against this input field.
        self.field = field


class NotFoundError(DomainError):
    status_code = 404
    default_code = "not_found"


class PermissionDeniedError(DomainError):
    status_code = 403
    default_code = "permission_denied"


class ConflictError(DomainError):
    status_code = 409
    default_code = "conflict"
