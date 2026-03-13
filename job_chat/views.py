from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from Core.throttling import ActionScopedRateThrottleMixin
from jobs.permissions import HasActiveJobAccess

from .models import JobChat, JobChatAttachment, JobChatMessage
from .permissions import IsJobChatMember
from .serializers import JobChatAttachmentSerializer, JobChatMessageSerializer, JobChatSerializer


@extend_schema_view(
    retrieve=extend_schema(
        summary="Get job chat",
        description="Returns the chat associated with an accessible job.",
    ),
    messages=extend_schema(
        summary="Manage chat messages",
        description="Gets messages or creates a new message in the selected chat.",
    ),
    attachments=extend_schema(
        summary="Attach file to message",
        description="Uploads a file and links it to an existing message in the selected chat.",
    ),
    download_attachment=extend_schema(
        summary="Get temporary attachment URL",
        description=(
            "Returns a temporary signed URL to download the chat attachment "
            "if the authorized user still has access to the chat."
        ),
    ),
)
class JobChatViewSet(
    ActionScopedRateThrottleMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = JobChatSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = JobChat.objects.select_related(
        "job",
        "job__user",
        "job__organization",
        "job__organization__user",
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "jobs"
    throttle_scope_action_map = {
        "retrieve": "jobs_read",
        ("messages", "get"): "jobs_read",
        ("messages", "post"): "jobs_messages",
        "attachments": "jobs_attachments",
        "download_attachment": "jobs_attachments",
    }

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "is_staff", False):
            return self.queryset
        return self.queryset.filter(
            Q(job__user=user) | Q(job__organization__user=user)
        ).distinct()

    def get_permissions(self):
        if self.action in {"retrieve", "messages", "attachments", "download_attachment"}:
            return [HasActiveJobAccess(), IsJobChatMember()]
        return [HasActiveJobAccess()]

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, uuid=None):
        chat = self.get_object()

        if request.method.lower() == "get":
            messages = (
                JobChatMessage.objects.select_related("sender", "chat")
                .prefetch_related("attachments")
                .filter(chat=chat)
                .order_by("created_at", "id")
            )
            page = self.paginate_queryset(messages)
            if page is not None:
                serializer = JobChatMessageSerializer(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

            serializer = JobChatMessageSerializer(messages, many=True, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = JobChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(chat=chat, sender=request.user)
        response_serializer = JobChatMessageSerializer(message, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"messages/(?P<message_id>\d+)/attachments",
        parser_classes=[MultiPartParser, FormParser],
    )
    def attachments(self, request, uuid=None, message_id=None):
        chat = self.get_object()

        message = JobChatMessage.objects.filter(id=message_id, chat=chat).first()
        if message is None:
            return Response({"detail": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
        if message.sender_id != request.user.id:
            return Response(
                {"detail": "Attachments can only be added to your own messages."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = JobChatAttachmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attachment = serializer.save(message=message, uploaded_by=request.user)
        response_serializer = JobChatAttachmentSerializer(attachment, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["get"],
        url_path=r"messages/(?P<message_id>\d+)/attachments/(?P<attachment_id>\d+)/download",
    )
    def download_attachment(self, request, uuid=None, message_id=None, attachment_id=None):
        chat = self.get_object()
        attachment = (
            JobChatAttachment.objects.select_related("message", "message__chat")
            .filter(id=attachment_id, message_id=message_id, message__chat=chat)
            .first()
        )
        if attachment is None:
            return Response({"detail": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)

        storage = attachment.file.storage
        ttl_seconds = getattr(settings, "JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS", 300)
        try:
            download_url = storage.url(attachment.file.name, expire=ttl_seconds)
        except TypeError:
            download_url = storage.url(attachment.file.name)

        if download_url.startswith("/"):
            download_url = request.build_absolute_uri(download_url)

        return Response(
            {
                "download_url": download_url,
                "expires_in": ttl_seconds,
                "filename": attachment.file.name.rsplit("/", 1)[-1],
            },
            status=status.HTTP_200_OK,
        )

