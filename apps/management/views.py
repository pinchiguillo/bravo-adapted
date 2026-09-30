import uuid

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assets.models import Asset
from apps.job_chat.models import JobChat
from apps.job_chat.serializers import JobChatMessageSerializer
from apps.jobs.models import Job
from apps.management.models import FeatureFlag
from apps.management.permissions import ensure_can_manage_user
from apps.notifications.services import emit_status_change_notification
from apps.organization.models import (
    AllowedCity,
    Announcement,
    AnnouncementStatusChange,
    Category,
    Organization,
    PlanTierCatalog,
    ServiceCatalog,
)
from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from .serializers import (
    ManagementAllowedCitySerializer,
    ManagementAnnouncementSerializer,
    ManagementAnnouncementStatusChangeSerializer,
    ManagementAssetSerializer,
    ManagementCategorySerializer,
    ManagementFeatureFlagSerializer,
    ManagementJobChatDetailSerializer,
    ManagementJobChatListSerializer,
    ManagementJobSerializer,
    ManagementOrganizationSerializer,
    ManagementPlanTierCatalogSerializer,
    ManagementServiceCatalogSerializer,
    ManagementUserSerializer,
)


class ManagementStatusActionsMixin:
    status_serializer_class = None

    def _set_status(self, request, status_value):
        instance = self.get_object()
        old_status = instance.status
        instance.status = status_value
        instance.save(update_fields=["status"])
        
        # Log the status change if it's an Announcement
        if hasattr(instance, 'status_changes'):
            from apps.organization.models import AnnouncementStatusChange
            reason_text = request.data.get('reason_text', '') if request.data else ''
            reason = request.data.get('reason', 'admin_decision') if request.data else 'admin_decision'
            
            AnnouncementStatusChange.objects.create(
                announcement=instance,
                from_status=old_status,
                to_status=status_value,
                reason=reason,
                reason_text=reason_text,
                changed_by='admin',
            )

        emit_status_change_notification(
            instance,
            old_status,
            status_value,
            actor=request.user if getattr(request.user, "is_authenticated", False) else None,
            reason_text=request.data.get("reason_text", "") if request.data else "",
        )
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="Activate managed resource")
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, *args, **kwargs):
        return self._set_status(request, self.status_serializer_class.ACTIVE)

    @extend_schema(summary="Deactivate managed resource")
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, *args, **kwargs):
        return self._set_status(request, self.status_serializer_class.INACTIVE)

    @extend_schema(summary="Suspend managed resource")
    @action(detail=True, methods=["post"], url_path="suspend")
    def suspend(self, request, *args, **kwargs):
        return self._set_status(request, self.status_serializer_class.SUSPENDED)


class ManagementFeatureFlagActionsMixin:
    def _set_active_state(self, is_active):
        instance = self.get_object()
        instance.is_active = is_active
        instance.save(update_fields=["is_active"])
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="Activate feature flag")
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, *args, **kwargs):
        return self._set_active_state(True)

    @extend_schema(summary="Deactivate feature flag")
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, *args, **kwargs):
        return self._set_active_state(False)


management_user_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Free text search over uuid, username, email, first name and last name.",
)

management_user_status_parameter = OpenApiParameter(
    name="status",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Exact user status filter.",
)

management_user_email_verified_parameter = OpenApiParameter(
    name="email_verified",
    type=bool,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Exact boolean filter for email verification status.",
)


@extend_schema(tags=["Management / Users"])
@extend_schema_view(
    list=extend_schema(
        tags=["Management / Users"],
        summary="List managed users",
        description="Returns the paginated list of managed users with optional search and filters.",
        parameters=[
            management_user_search_parameter,
            management_user_status_parameter,
            management_user_email_verified_parameter,
        ],
    ),
)
class ManagementUserViewSet(
    ActionScopedRateThrottleMixin,
    ManagementStatusActionsMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementUserSerializer
    queryset = get_user_model().objects.select_related("organization").all().order_by("id")
    lookup_field = "uuid"
    status_serializer_class = get_user_model().Status
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "activate": "management_status",
        "deactivate": "management_status",
        "suspend": "management_status",
    }

    write_actions = {"update", "partial_update", "activate", "deactivate", "suspend"}

    def get_object(self):
        user = super().get_object()
        if self.action in self.write_actions:
            ensure_can_manage_user(self.request.user, user, self.action)
        return user

    def get_queryset(self):
        queryset = self.queryset
        if self.action != "list":
            return queryset

        search_query = str(self.request.query_params.get("search", "")).strip()
        if search_query:
            search_filter = (
                Q(username__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
            )
            search_uuid = self._parse_uuid(search_query)
            if search_uuid is not None:
                search_filter |= Q(uuid=search_uuid)
            queryset = queryset.filter(search_filter)

        status_value = str(self.request.query_params.get("status", "")).strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        email_verified = self.request.query_params.get("email_verified")
        if email_verified is not None and str(email_verified).strip() != "":
            queryset = queryset.filter(email_verified=self._parse_boolean_query_param(email_verified))

        return queryset

    def _parse_boolean_query_param(self, raw_value):
        normalized_value = str(raw_value).strip().lower()
        if normalized_value in {"true", "1"}:
            return True
        if normalized_value in {"false", "0"}:
            return False
        raise ValidationError(
            {"email_verified": "Use a boolean value: true or false."}
        )

    def _parse_uuid(self, raw_value):
        try:
            return uuid.UUID(str(raw_value).strip())
        except (AttributeError, TypeError, ValueError):
            return None


def parse_optional_uuid(raw_value):
    try:
        return uuid.UUID(str(raw_value).strip())
    except (AttributeError, TypeError, ValueError):
        return None


@extend_schema(tags=["Management / Feature Flags"])
class ManagementFeatureFlagViewSet(
    ActionScopedRateThrottleMixin,
    ManagementFeatureFlagActionsMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementFeatureFlagSerializer
    queryset = FeatureFlag.objects.all().order_by("key")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "activate": "management_status",
        "deactivate": "management_status",
    }


@extend_schema(tags=["Management / Categories"])
class ManagementCategoryViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementCategorySerializer
    queryset = Category.objects.all().order_by("name")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
    }


@extend_schema(tags=["Management / Allowed Cities"])
class ManagementAllowedCityViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementAllowedCitySerializer
    queryset = AllowedCity.objects.all().order_by("name")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
    }


@extend_schema(tags=["Management / Plan Tiers"])
class ManagementPlanTierCatalogViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementPlanTierCatalogSerializer
    queryset = PlanTierCatalog.objects.all().order_by("sort_order", "name")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
    }


management_announcement_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Free text search over announcement title, description, location, category and services.",
)


management_announcement_status_parameter = OpenApiParameter(
    name="status",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Exact announcement status filter.",
)

management_job_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Free text search over job UUID, status, requester, provider, and announcement fields.",
)

management_job_status_parameter = OpenApiParameter(
    name="status",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Exact job status filter.",
)

management_chat_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Free text search over chat UUID, job UUID, participants, announcement, and message content.",
)


@extend_schema(tags=["Management / Announcements"])
@extend_schema_view(
    list=extend_schema(
        tags=["Management / Announcements"],
        summary="List managed announcements",
        description="Returns the paginated list of announcements for administrative management.",
        parameters=[management_announcement_search_parameter, management_announcement_status_parameter],
    ),
)
@extend_schema(tags=["Management / Announcements"])
class ManagementAnnouncementViewSet(
    ManagementStatusActionsMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementAnnouncementSerializer
    status_serializer_class = Announcement.Status
    queryset = Announcement.objects.select_related("organization", "category").prefetch_related(
        "images", "subservices__service_catalog__category", "subservices__price_table"
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
        "activate": "management_write",
        "deactivate": "management_write",
        "suspend": "management_write",
    }

    def get_queryset(self):
        queryset = self.queryset.order_by("-created_at", "-id")

        if self.action != "list":
            return queryset

        search_query = str(self.request.query_params.get("search", "")).strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(location__icontains=search_query)
                | Q(announcement__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(free_text__icontains=search_query)
                | Q(category__name__icontains=search_query)
                | Q(subservices__service_catalog__name__icontains=search_query)
                | Q(status__icontains=search_query)
            )

        status_value = str(self.request.query_params.get("status", "")).strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        return queryset.distinct()


@extend_schema(tags=["Management / Jobs"])
@extend_schema_view(
    list=extend_schema(
        tags=["Management / Jobs"],
        summary="List managed jobs",
        description="Returns the paginated list of jobs for administrative management.",
        parameters=[management_job_search_parameter, management_job_status_parameter],
    ),
)
class ManagementJobViewSet(
    ManagementStatusActionsMixin,
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementJobSerializer
    queryset = (
        Job.objects.select_related(
            "user",
            "announcement",
            "announcement__organization",
            "plan_price",
            "chat",
        )
        .order_by("-created_at", "-id")
    )
    lookup_field = "uuid"
    status_serializer_class = Job.Status
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "activate": "management_status",
        "deactivate": "management_status",
        "suspend": "management_status",
    }

    def get_queryset(self):
        queryset = self.queryset
        if self.action == "list":
            search_query = str(self.request.query_params.get("search", "")).strip()
            if search_query:
                search_filter = (
                    Q(status__icontains=search_query)
                    | Q(user__username__icontains=search_query)
                    | Q(user__email__icontains=search_query)
                    | Q(user__first_name__icontains=search_query)
                    | Q(user__last_name__icontains=search_query)
                    | Q(announcement__name__icontains=search_query)
                    | Q(announcement__location__icontains=search_query)
                    | Q(announcement__organization__name__icontains=search_query)
                )
                search_uuid = parse_optional_uuid(search_query)
                if search_uuid is not None:
                    search_filter |= Q(uuid=search_uuid)
                queryset = queryset.filter(search_filter)

            status_value = str(self.request.query_params.get("status", "")).strip()
            if status_value:
                queryset = queryset.filter(status=status_value)

        return queryset


@extend_schema(tags=["Management / Chats"])
@extend_schema_view(
    list=extend_schema(
        tags=["Management / Chats"],
        summary="List managed chats",
        description="Returns the paginated list of job chats for administrative inspection.",
        parameters=[management_chat_search_parameter],
    ),
    retrieve=extend_schema(
        tags=["Management / Chats"],
        summary="Get managed chat detail",
        description="Returns the full chat thread for a job chat by job UUID.",
    ),
)
class ManagementChatViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
    }
    lookup_field = "job__uuid"
    lookup_url_kwarg = "job_uuid"

    def get_queryset(self):
        queryset = JobChat.objects.select_related(
            "job",
            "job__user",
            "job__announcement",
            "job__announcement__organization",
        ).prefetch_related("messages__attachments__asset")

        search_query = str(self.request.query_params.get("search", "")).strip()
        if search_query:
            search_filter = (
                Q(job__status__icontains=search_query)
                | Q(job__user__username__icontains=search_query)
                | Q(job__user__email__icontains=search_query)
                | Q(job__announcement__name__icontains=search_query)
                | Q(job__announcement__organization__name__icontains=search_query)
                | Q(messages__content__icontains=search_query)
            )
            search_uuid = parse_optional_uuid(search_query)
            if search_uuid is not None:
                search_filter |= Q(uuid=search_uuid) | Q(job__uuid=search_uuid)
            queryset = queryset.filter(search_filter)

        return queryset.annotate(message_count=Count("messages", distinct=True)).distinct().order_by(
            "-updated_at",
            "-id",
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ManagementJobChatDetailSerializer
        return ManagementJobChatListSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        chats = list(queryset)
        self._attach_last_messages(chats)
        page = self.paginate_queryset(chats)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(chats, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        chat = self.get_object()
        messages_queryset = chat.messages.select_related("user").prefetch_related("attachments__asset").order_by(
            "created_at",
            "id",
        )
        page = self.paginator.paginate_queryset(messages_queryset, request, view=self)
        if page is None:
            page_payload = {
                "count": messages_queryset.count(),
                "next": None,
                "previous": None,
                "results": [],
            }
            messages = messages_queryset
        else:
            messages = page
            page_payload = self.paginator.get_paginated_response(
                []
            ).data

        serializer = self.get_serializer(chat)
        data = serializer.data
        message_serializer = JobChatMessageSerializer(messages, many=True)
        page_payload["results"] = message_serializer.data
        data["messages"] = page_payload
        return Response(data)

    def _attach_last_messages(self, chats):
        for chat in chats:
            chat._prefetched_last_message = chat.messages.order_by("-created_at", "-id").first()


@extend_schema(tags=["Management / Services"])
class ManagementServiceCatalogViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementServiceCatalogSerializer
    queryset = ServiceCatalog.objects.select_related("category").order_by("name", "uuid")
    lookup_field = "uuid"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "destroy": "management_write",
    }


@extend_schema(tags=["Management / Organizations"])
class ManagementOrganizationViewSet(
    ActionScopedRateThrottleMixin,
    ManagementStatusActionsMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementOrganizationSerializer
    queryset = (
        Organization.objects.select_related("user", "pricing", "pricing__plan_tier")
        .with_rating()
        .order_by("name")
    )
    lookup_field = "uuid"
    status_serializer_class = Organization.Status
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "create": "management_write",
        "update": "management_write",
        "partial_update": "management_write",
        "activate": "management_status",
        "deactivate": "management_status",
        "suspend": "management_status",
    }


@extend_schema(tags=["Management / Announcements"])
class ManagementAnnouncementStatusChangeViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only ViewSet for tracking announcement status changes."""

    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementAnnouncementStatusChangeSerializer
    queryset = AnnouncementStatusChange.objects.select_related("announcement").order_by("-created_at")
    filterset_fields = ["announcement__uuid", "to_status", "reason"]
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
    }

    def get_queryset(self):
        queryset = self.queryset
        announcement_uuid = self.request.query_params.get("announcement__uuid")
        if announcement_uuid:
            queryset = queryset.filter(announcement__uuid=announcement_uuid)
        return queryset


@extend_schema(tags=["Management / Stats"])
class ManagementStatsView(APIView):
    """Returns aggregate counts for all management entities in a single request."""

    permission_classes = [IsActiveAccount, permissions.IsAdminUser]

    @extend_schema(
        summary="Get management statistics",
        description="Aggregated counts for users, organizations, announcements, jobs and catalogs.",
    )
    def get(self, request):
        User = get_user_model()

        return Response({
            "users": {
                "total": User.objects.count(),
                "active": User.objects.filter(status="active").count(),
                "inactive": User.objects.filter(status="inactive").count(),
                "suspended": User.objects.filter(status="suspended").count(),
                "email_verified": User.objects.filter(email_verified=True).count(),
                "staff": User.objects.filter(is_staff=True).count(),
            },
            "organizations": {
                "total": Organization.objects.count(),
                "active": Organization.objects.filter(status="active").count(),
                "inactive": Organization.objects.filter(status="inactive").count(),
                "suspended": Organization.objects.filter(status="suspended").count(),
            },
            "announcements": {
                "total": Announcement.objects.count(),
                "active": Announcement.objects.filter(status="active").count(),
                "draft": Announcement.objects.filter(status="draft").count(),
                "paused": Announcement.objects.filter(status="paused").count(),
                "closed": Announcement.objects.filter(status="closed").count(),
                "published": Announcement.objects.filter(status="published").count(),
            },
            "jobs": {
                "total": Job.objects.count(),
                "pending": Job.objects.filter(status="pending").count(),
                "active": Job.objects.filter(status="active").count(),
                "completed": Job.objects.filter(status="completed").count(),
                "rejected": Job.objects.filter(status="rejected").count(),
                "suspended": Job.objects.filter(status="suspended").count(),
                "inactive": Job.objects.filter(status="inactive").count(),
            },
            "catalogs": {
                "categories": Category.objects.count(),
                "services": ServiceCatalog.objects.count(),
                "allowed_cities": AllowedCity.objects.count(),
            },
        })


@extend_schema(tags=["Management / Assets"])
class ManagementAssetViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementAssetSerializer
    queryset = Asset.objects.select_related("owner").order_by("-created_at")
    lookup_field = "id"
    throttle_scope_prefix = "management"
    throttle_scope_action_map = {
        "list": "management_read",
        "retrieve": "management_read",
        "destroy": "management_write",
    }

    def get_queryset(self):
        queryset = self.queryset
        if self.action != "list":
            return queryset

        search_query = str(self.request.query_params.get("search", "")).strip()
        if search_query:
            queryset = queryset.filter(original_filename__icontains=search_query)

        kind_value = str(self.request.query_params.get("kind", "")).strip()
        if kind_value:
            queryset = queryset.filter(kind=kind_value)

        status_value = str(self.request.query_params.get("status", "")).strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        return queryset


@extend_schema(tags=["Management / Assets"])
class ManagementAssetStatsView(APIView):
    """Returns aggregate statistics for assets."""

    permission_classes = [IsActiveAccount, permissions.IsAdminUser]

    @extend_schema(
        summary="Get asset statistics",
        description="Aggregated counts and sizes for assets by kind and status.",
    )
    def get(self, request):
        base_queryset = Asset.objects.all()

        # Total count and size
        total_count = base_queryset.count()
        total_size = base_queryset.aggregate(total=Sum("size_actual"))["total"] or 0

        # By kind
        by_kind = dict(
            base_queryset
            .values("kind")
            .annotate(count=Count("id"))
            .values_list("kind", "count")
        )

        # By status
        by_status = dict(
            base_queryset
            .values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        return Response({
            "total": total_count,
            "total_size_bytes": total_size,
            "by_kind": by_kind,
            "by_status": by_status,
        })
