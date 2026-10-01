from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework import permissions

if TYPE_CHECKING:
    # Type-only: DRF imports this module (DEFAULT_PERMISSION_CLASSES) while
    # rest_framework.views is still initialising.
    from rest_framework.request import Request
    from rest_framework.views import APIView


def get_active_account_denial_message(user: Any) -> str | None:
    if not user.is_active:
        return "User account is inactive."
    if hasattr(user, "Status") and getattr(user, "status", None) != user.Status.ACTIVE:
        return "User account is not active."
    return None


def user_has_active_account(user: Any) -> bool:
    return get_active_account_denial_message(user) is None


def user_can_authenticate(user: Any) -> bool:
    """SimpleJWT USER_AUTHENTICATION_RULE: only active, non-suspended accounts get tokens."""
    return user is not None and user_has_active_account(user)


def get_email_verification_denial_message(user: Any) -> str | None:
    if hasattr(user, "is_email_verified"):
        if user.is_email_verified:
            return None
        return "Email is not verified."
    if hasattr(user, "email_verified") and not user.email_verified:
        return "Email is not verified."
    return None


def user_has_email_verified_or_bypass(user: Any) -> bool:
    return get_email_verification_denial_message(user) is None


class IsActiveAccount(permissions.IsAuthenticated):
    message = "User account is not allowed to access this endpoint."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        denial_message = get_active_account_denial_message(request.user)
        if denial_message is not None:
            self.message = denial_message
            return False
        return True
