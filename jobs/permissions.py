from rest_framework import permissions

from Core.permissions import (
    get_active_account_denial_message,
    get_email_verification_denial_message,
    user_has_active_account,
    user_has_email_verified_or_bypass,
)


def user_has_jobs_access(user):
    if not user_has_active_account(user):
        return False
    if not user_has_email_verified_or_bypass(user):
        return False
    return True


class HasActiveJobAccess(permissions.BasePermission):
    message = "User account is not allowed to access jobs."

    def has_permission(self, request, view):
        if not user_has_jobs_access(request.user):
            denial_message = get_active_account_denial_message(request.user)
            if denial_message is not None:
                self.message = denial_message
            else:
                self.message = (
                    get_email_verification_denial_message(request.user)
                    or "User account is not allowed to access jobs."
                )
            return False
        return True


class IsJobMember(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not user_has_jobs_access(request.user):
            return False
        return obj.user_id == request.user.id or obj.organization.user_id == request.user.id
