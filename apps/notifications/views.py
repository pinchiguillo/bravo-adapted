from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from .models import Notification, NotificationPreference, NotificationRecipient, NotificationTemplate
from .serializers import (
    ManagementNotificationSerializer,
    ManagementSendNotificationSerializer,
    NotificationPreferenceSerializer,
    NotificationRecipientSerializer,
    NotificationTemplateSerializer,
    NotificationUnreadCountSerializer,
)


@extend_schema(tags=["Notifications"])
@extend_schema_view(
    list=extend_schema(
        summary="List inbox notifications",
        responses=NotificationRecipientSerializer(many=True),
    ),
)
class NotificationViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount]
    serializer_class = NotificationRecipientSerializer
    throttle_scope_prefix = "notifications"
    throttle_scope_action_map = {
        "list": "notifications_read",
        "unread_count": "notifications_read",
        "read": "notifications_write",
        "mark_all_read": "notifications_write",
    }
    lookup_field = "uuid"

    def get_queryset(self):
        return (
            NotificationRecipient.objects.select_related("notification")
            .filter(user=self.request.user, in_app_enabled=True)
            .order_by("-notification__created_at", "-id")
        )

    @extend_schema(
        summary="Get unread inbox count",
        responses=NotificationUnreadCountSerializer,
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request, *args, **kwargs):
        unread_count = self.get_queryset().filter(read_at__isnull=True).count()
        serializer = NotificationUnreadCountSerializer({"unread_count": unread_count})
        return Response(serializer.data)

    @extend_schema(summary="Mark one notification as read")
    @action(detail=True, methods=["post"], url_path="read")
    def read(self, request, *args, **kwargs):
        recipient = self.get_object()
        if recipient.read_at is None:
            recipient.read_at = timezone.now()
            recipient.save(update_fields=["read_at", "updated_at"])
        serializer = self.get_serializer(recipient)
        return Response(serializer.data)

    @extend_schema(summary="Mark all notifications as read")
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request, *args, **kwargs):
        updated_count = (
            self.get_queryset()
            .filter(read_at__isnull=True)
            .update(
                read_at=timezone.now(),
            )
        )
        return Response({"updated_count": updated_count}, status=status.HTTP_200_OK)


@extend_schema(tags=["Notifications"])
class NotificationPreferenceView(APIView):
    permission_classes = [IsActiveAccount]

    def get(self, request, *args, **kwargs):
        preferences, _ = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(preferences)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        preferences, _ = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(
            preferences,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema(tags=["Management / Notifications"])
class ManagementNotificationViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementNotificationSerializer
    queryset = Notification.objects.select_related("created_by").prefetch_related("recipients")
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "send": "management_write",
    }
    lookup_field = "uuid"

    def get_queryset(self):
        queryset = self.queryset.order_by("-created_at", "-id")
        origin = str(self.request.query_params.get("origin", "")).strip()
        channel = str(self.request.query_params.get("channel", "")).strip()
        delivery_status = str(self.request.query_params.get("status", "")).strip()
        search = str(self.request.query_params.get("search", "")).strip()

        if origin:
            queryset = queryset.filter(origin=origin)

        if channel:
            if channel == Notification.Channel.IN_APP:
                queryset = queryset.filter(recipients__in_app_enabled=True)
            elif channel == Notification.Channel.EMAIL:
                queryset = queryset.filter(recipients__email_enabled=True)
            elif channel == Notification.Channel.PUSH:
                queryset = queryset.filter(recipients__push_enabled=True)

        if delivery_status:
            queryset = queryset.filter(
                Q(recipients__email_status=delivery_status) | Q(recipients__push_status=delivery_status)
            )

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(body__icontains=search)
                | Q(target_label__icontains=search)
                | Q(recipients__user__email__icontains=search)
                | Q(recipients__user__username__icontains=search)
            )

        return queryset.distinct()

    @extend_schema(
        summary="Send an administrative notification",
        request=ManagementSendNotificationSerializer,
        responses=ManagementNotificationSerializer,
    )
    @action(detail=False, methods=["post"], url_path="send")
    def send(self, request, *args, **kwargs):
        serializer = ManagementSendNotificationSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        notification = serializer.save()
        output_serializer = self.get_serializer(notification)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Management / Notifications"])
class ManagementNotificationTemplateViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = NotificationTemplateSerializer
    queryset = NotificationTemplate.objects.all().order_by("key")
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
    }
    lookup_field = "uuid"
