from rest_framework import permissions

from jobs.permissions import user_has_jobs_access


class IsJobChatMember(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not user_has_jobs_access(request.user):
            return False
        job = obj.job
        return job.user_id == request.user.id or job.organization.user_id == request.user.id

