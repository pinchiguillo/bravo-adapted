from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from Core.permissions import IsActiveAccount
from Core.throttling import ActionScopedRateThrottleMixin

from .models import (
    RgpdAnonymousConsent,
    RgpdAnonymousConsentEvent,
    RgpdConsent,
    RgpdConsentEvent,
)
from .serializers import (
    RgpdAnonymousConsentSerializer,
    RgpdAnonymousConsentUpsertSerializer,
    RgpdConsentSerializer,
    RgpdConsentUpsertSerializer,
)
from .utils import (
    extract_client_ip,
    generate_anonymous_identifier,
    generate_write_token,
    hash_write_token,
    verify_write_token,
)


class RgpdConsentViewSet(ActionScopedRateThrottleMixin, viewsets.GenericViewSet):
    queryset = RgpdConsent.objects.select_related("user")
    serializer_class = RgpdConsentSerializer
    permission_classes = [IsActiveAccount]
    throttle_scope_prefix = "rgpd"
    throttle_scope_action_map = {
        "me": "rgpd_authenticated_read",
        "create_me": "rgpd_authenticated_write",
        "update_me": "rgpd_authenticated_write",
    }

    def get_serializer_class(self):
        if self.action in {"create_me", "update_me"}:
            return RgpdConsentUpsertSerializer
        return RgpdConsentSerializer

    def _get_or_initialize_consent(self):
        consent = RgpdConsent.objects.filter(user=self.request.user).first()
        if consent is not None:
            return consent
        return RgpdConsent(user=self.request.user)

    def _save_consent(self, request, partial):
        consent = self._get_or_initialize_consent()
        action = RgpdConsentEvent.Action.UPSERT if consent.pk is None else RgpdConsentEvent.Action.UPDATE
        serializer = self.get_serializer(consent, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        validated_data["ip_address"] = extract_client_ip(request)
        validated_data["user_agent"] = request.META.get("HTTP_USER_AGENT", "")
        consent.apply_acceptance_changes(validated_data)
        consent.save()
        RgpdConsentEvent.objects.create(consent=consent, action=action, **consent.build_event_payload())
        return Response(RgpdConsentSerializer(consent).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="me")
    @extend_schema(
        tags=["RGPD"],
        summary="Obtener mis consentimientos RGPD",
        description="Devuelve el estado actual de aceptacion de cookies, politicas y terminos del usuario autenticado.",
        responses=RgpdConsentSerializer,
    )
    def me(self, request):
        consent = self._get_or_initialize_consent()
        return Response(RgpdConsentSerializer(consent).data, status=status.HTTP_200_OK)

    @me.mapping.post
    @extend_schema(
        tags=["RGPD"],
        summary="Registrar consentimientos RGPD",
        description="Crea o reemplaza el estado de consentimientos RGPD del usuario autenticado y registra metadatos de trazabilidad.",
        request=RgpdConsentUpsertSerializer,
        responses=RgpdConsentSerializer,
    )
    def create_me(self, request):
        return self._save_consent(request, partial=False)

    @me.mapping.patch
    @extend_schema(
        tags=["RGPD"],
        summary="Actualizar consentimientos RGPD",
        description="Actualiza parcialmente el estado de consentimientos RGPD del usuario autenticado y refresca los metadatos enviados.",
        request=RgpdConsentUpsertSerializer,
        responses=RgpdConsentSerializer,
    )
    def update_me(self, request):
        return self._save_consent(request, partial=True)


@extend_schema_view(
    create=extend_schema(
        tags=["RGPD"],
        summary="Registrar consentimiento RGPD anonimo",
        description=(
            "Crea un consentimiento RGPD anonimo con identificador y token de escritura "
            "generados por el servidor, o actualiza uno existente cuando se aportan ambos."
        ),
        request=RgpdAnonymousConsentUpsertSerializer,
        responses={200: RgpdAnonymousConsentSerializer, 201: RgpdAnonymousConsentSerializer},
    ),
)
class RgpdAnonymousConsentViewSet(ActionScopedRateThrottleMixin, viewsets.GenericViewSet):
    queryset = RgpdAnonymousConsent.objects.all()
    serializer_class = RgpdAnonymousConsentUpsertSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope_prefix = "rgpd"
    throttle_scope_action_map = {
        "create": "rgpd_anonymous_write",
    }

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consent, write_token, action, status_code = self._resolve_anonymous_consent(serializer.validated_data)

        validated_data = dict(serializer.validated_data)
        validated_data.pop("identifier", None)
        validated_data.pop("write_token", None)
        validated_data["ip_address"] = extract_client_ip(request)
        validated_data["user_agent"] = request.META.get("HTTP_USER_AGENT", "")
        consent.apply_acceptance_changes(validated_data)
        consent.save()
        RgpdAnonymousConsentEvent.objects.create(
            consent=consent,
            action=action,
            **consent.build_event_payload(),
        )

        response_data = dict(RgpdAnonymousConsentSerializer(consent).data)
        if write_token is not None:
            response_data["write_token"] = write_token
        return Response(response_data, status=status_code)

    def _resolve_anonymous_consent(self, validated_data):
        identifier = validated_data.get("identifier")
        write_token = validated_data.get("write_token")
        if identifier and write_token:
            consent = RgpdAnonymousConsent.objects.filter(identifier=identifier).first()
            if consent is None or not verify_write_token(consent.write_token_hash, write_token):
                raise NotFound("Anonymous consent not found.")
            return consent, None, RgpdAnonymousConsentEvent.Action.UPDATE, status.HTTP_200_OK

        write_token = generate_write_token()
        consent = RgpdAnonymousConsent(
            identifier=generate_anonymous_identifier(),
            write_token_hash=hash_write_token(write_token),
        )
        return consent, write_token, RgpdAnonymousConsentEvent.Action.CREATE, status.HTTP_201_CREATED
