from rest_framework import permissions


def get_resource_organization_owner_id(obj):
    if hasattr(obj, "user_id"):
        return obj.user_id

    organization = getattr(obj, "organization", None)
    if organization is not None:
        return organization.user_id

    service = getattr(obj, "service", None)
    if service is not None:
        return service.organization.user_id

    subservice = getattr(obj, "subservice", None)
    if subservice is not None:
        return subservice.service.organization.user_id

    return None


class IsOrganizationResourceOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        return get_resource_organization_owner_id(obj) == request.user.id
