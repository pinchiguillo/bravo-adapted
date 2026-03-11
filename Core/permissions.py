from rest_framework import permissions


def get_active_account_denial_message(user):
    if not user.is_active:
        return "User account is inactive."
    if hasattr(user, "Status") and getattr(user, "status", None) != user.Status.ACTIVE:
        return "User account is not active."
    return None


def user_has_active_account(user):
    return get_active_account_denial_message(user) is None


class IsActiveAccount(permissions.IsAuthenticated):
    message = "User account is not allowed to access this endpoint."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        denial_message = get_active_account_denial_message(request.user)
        if denial_message is not None:
            self.message = denial_message
            return False
        return True
