from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from Core.throttling import ActionScopedRateThrottleMixin

from .models import Job, JobChatAttachment, JobChatMessage
from .permissions import HasActiveJobAccess, IsJobMember
from .serializers import JobChatAttachmentSerializer, JobChatMessageSerializer, JobSerializer


@extend_schema_view(
    list=extend_schema(
        summary="Listar trabajos",
        description="Lista los trabajos donde el usuario autenticado participa como cliente o como organizacion.",
    ),
    create=extend_schema(
        summary="Crear trabajo",
        description="Crea un nuevo trabajo asociado al usuario autenticado.",
    ),
    retrieve=extend_schema(
        summary="Obtener trabajo",
        description="Devuelve el detalle de un trabajo accesible para el usuario autenticado.",
    ),
    update=extend_schema(
        summary="Reemplazar trabajo",
        description="Reemplaza completamente un trabajo accesible para el usuario autenticado.",
    ),
    partial_update=extend_schema(
        summary="Actualizar trabajo",
        description="Actualiza parcialmente un trabajo accesible para el usuario autenticado.",
    ),
    destroy=extend_schema(
        summary="Eliminar trabajo",
        description="Elimina un trabajo accesible para el usuario autenticado.",
    ),
    messages=extend_schema(
        summary="Gestionar mensajes del trabajo",
        description="Obtiene los mensajes del chat del trabajo o crea un nuevo mensaje en ese chat.",
    ),
    attachments=extend_schema(
        summary="Adjuntar archivo a mensaje",
        description="Sube un archivo y lo vincula a un mensaje existente dentro del chat del trabajo.",
    ),
    download_attachment=extend_schema(
        summary="Obtener URL temporal de adjunto",
        description=(
            "Devuelve una URL temporal firmada para descargar el adjunto del chat "
            "si el usuario autorizado sigue teniendo acceso al job."
        ),
    ),
)
class JobViewSet(ActionScopedRateThrottleMixin, viewsets.ModelViewSet):
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Job.objects.select_related(
        "user",
        "organization",
        "organization__user",
        "plan_price",
        "plan_price__service",
        "chat",
    )
    lookup_field = "uuid"
    throttle_scope_prefix = "jobs"
    throttle_scope_action_map = {
        "list": "jobs_read",
        "retrieve": "jobs_read",
        "create": "jobs_write",
        "update": "jobs_write",
        "partial_update": "jobs_write",
        "destroy": "jobs_write",
        ("messages", "get"): "jobs_read",
        ("messages", "post"): "jobs_messages",
        "attachments": "jobs_attachments",
        "download_attachment": "jobs_attachments",
    }

    def get_queryset(self):
        if getattr(self.request.user, "is_staff", False):
            return self.queryset
        user = self.request.user
        return self.queryset.filter(Q(user=user) | Q(organization__user=user)).distinct()

    def get_permissions(self):
        if self.action == "destroy":
            return [HasActiveJobAccess(), permissions.IsAdminUser()]
        if self.action in {"retrieve", "update", "partial_update", "messages", "attachments", "download_attachment"}:
            return [HasActiveJobAccess(), IsJobMember()]
        return [HasActiveJobAccess()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, uuid=None):
        job = self.get_object()

        if request.method.lower() == "get":
            messages = (
                JobChatMessage.objects.select_related("sender", "chat")
                .prefetch_related("attachments")
                .filter(chat__job=job)
                .order_by("created_at", "id")
            )
            serializer = JobChatMessageSerializer(messages, many=True, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = JobChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(chat=job.chat, sender=request.user)
        response_serializer = JobChatMessageSerializer(message, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"messages/(?P<message_id>\d+)/attachments",
        parser_classes=[MultiPartParser, FormParser],
    )
    def attachments(self, request, uuid=None, message_id=None):
        job = self.get_object()

        message = JobChatMessage.objects.filter(id=message_id, chat__job=job).first()
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
        job = self.get_object()
        attachment = (
            JobChatAttachment.objects.select_related("message", "message__chat", "message__chat__job")
            .filter(id=attachment_id, message_id=message_id, message__chat__job=job)
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
