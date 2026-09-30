from rest_framework.exceptions import PermissionDenied

ROLE_FIELDS = ("is_staff", "is_superuser")
SELF_LOCKOUT_FIELDS = ("is_staff", "is_superuser", "is_active", "status")
STATUS_ACTIONS = {"activate", "deactivate", "suspend"}


def is_privileged(user):
    return bool(user.is_staff or user.is_superuser)


def ensure_can_manage_user(actor, target, action):
    """Guard write actions on user accounts from the management API.

    Staff users manage regular accounts only; changing a staff or superuser
    account (password, email, status...) would let them take it over, so that
    is reserved to superusers. Nobody can change their own account status.
    """
    if target.pk == actor.pk and action in STATUS_ACTIONS:
        raise PermissionDenied("You cannot change the status of your own account.")
    if not actor.is_superuser and is_privileged(target):
        raise PermissionDenied("Only superusers can modify staff or superuser accounts.")


def ensure_can_change_roles(actor, target, submitted_fields):
    """Only superusers grant or revoke roles, and never on their own account."""
    if target.pk == actor.pk and any(field in submitted_fields for field in SELF_LOCKOUT_FIELDS):
        raise PermissionDenied("You cannot change the role or status of your own account.")
    if not actor.is_superuser and any(field in submitted_fields for field in ROLE_FIELDS):
        raise PermissionDenied("Only superusers can grant or revoke staff or superuser roles.")
