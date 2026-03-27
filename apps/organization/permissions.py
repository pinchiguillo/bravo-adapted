from rest_framework import permissions


class IsOrganizationOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and obj.user_id == request.user.id


class IsServiceOrganizationOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and obj.organization.user_id == request.user.id


class IsAnnouncementOrganizationOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and obj.organization.user_id == request.user.id
