from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from common.permissions import IsActiveAccount
from common.throttling import ActionScopedRateThrottleMixin

from .models import (
    RgpdAnonymousConsent,
    RgpdAnonymousConsentEvent,
    RgpdConsent,
    RgpdConsentEvent,
    RgpdDataRequest,
    RgpdLegalDocument,
    RgpdPolicyDocument,
    RgpdPolicyVersion,
)
from .serializers import (
    ManagementRgpdDataRequestSerializer,
    ManagementRgpdDataRequestUpdateSerializer,
    ManagementRgpdPolicyDocumentSerializer,
    ManagementRgpdPolicyVersionCreateSerializer,
    ManagementRgpdPolicyVersionSerializer,
    RgpdAnonymousConsentSerializer,
    RgpdAnonymousConsentUpsertSerializer,
    RgpdConsentSerializer,
    RgpdConsentUpsertSerializer,
    RgpdDataRequestCreateSerializer,
    RgpdDataRequestSerializer,
    RgpdLegalDocumentSerializer,
    RgpdPublicPolicyVersionSerializer,
)
from .services import publish_policy_version, record_policy_acceptances, set_data_request_status
from .utils import (
    extract_client_ip,
    generate_anonymous_identifier,
    generate_write_token,
    hash_write_token,
    verify_write_token,
)


@extend_schema(tags=["RGPD"])
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
        try:
            record_policy_acceptances(
                validated_data=validated_data,
                source=validated_data.get("source", ""),
                ip_address=validated_data["ip_address"],
                user_agent=validated_data["user_agent"],
                user=request.user,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        consent.apply_acceptance_changes(validated_data)
        consent.save()
        RgpdConsentEvent.objects.create(
            consent=consent,
            action=action,
            **consent.build_event_payload(),
        )
        return Response(RgpdConsentSerializer(consent).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="me")
    @extend_schema(
        tags=["RGPD"],
        summary="Get my GDPR consents",
        description="Returns the current acceptance state of cookies, policies, and terms for the authenticated user.",
        responses=RgpdConsentSerializer,
    )
    def me(self, request):
        consent = self._get_or_initialize_consent()
        return Response(RgpdConsentSerializer(consent).data, status=status.HTTP_200_OK)

    @me.mapping.post
    @extend_schema(
        tags=["RGPD"],
        summary="Register GDPR consents",
        description=(
            "Creates or replaces the GDPR consent state of the authenticated user "
            "and records traceability metadata."
        ),
        request=RgpdConsentUpsertSerializer,
        responses=RgpdConsentSerializer,
    )
    def create_me(self, request):
        return self._save_consent(request, partial=False)

    @me.mapping.patch
    @extend_schema(
        tags=["RGPD"],
        summary="Update GDPR consents",
        description=(
            "Partially updates the GDPR consent state of the authenticated user "
            "and refreshes submitted metadata."
        ),
        request=RgpdConsentUpsertSerializer,
        responses=RgpdConsentSerializer,
    )
    def update_me(self, request):
        return self._save_consent(request, partial=True)


@extend_schema_view(
    create=extend_schema(
        tags=["RGPD"],
        summary="Register anonymous GDPR consent",
        description=(
            "Creates an anonymous GDPR consent with server-generated identifier and "
            "write token, or updates an existing one when both are provided."
        ),
        request=RgpdAnonymousConsentUpsertSerializer,
        responses={200: RgpdAnonymousConsentSerializer, 201: RgpdAnonymousConsentSerializer},
        auth=[],
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
        try:
            record_policy_acceptances(
                validated_data=validated_data,
                source=validated_data.get("source", ""),
                ip_address=validated_data["ip_address"],
                user_agent=validated_data["user_agent"],
                anonymous_consent=consent,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

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
        consent.save()
        return consent, write_token, RgpdAnonymousConsentEvent.Action.CREATE, status.HTTP_201_CREATED


@extend_schema_view(
    list=extend_schema(
        tags=["RGPD"],
        summary="List current published RGPD documents",
        description="Returns the currently published public versions for privacy, terms, and cookies.",
        responses=RgpdPublicPolicyVersionSerializer(many=True),
        auth=[],
    ),
)
class RgpdPublicPolicyViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = RgpdPublicPolicyVersionSerializer
    permission_classes = [permissions.AllowAny]
    queryset = RgpdPolicyVersion.objects.select_related("document").filter(
        is_published=True,
        is_current=True,
    )

    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        tags=["RGPD"],
        summary="List my RGPD requests",
        responses=RgpdDataRequestSerializer(many=True),
    ),
    create=extend_schema(
        tags=["RGPD"],
        summary="Create RGPD request",
        request=RgpdDataRequestCreateSerializer,
        responses={201: RgpdDataRequestSerializer},
    ),
)
class RgpdDataRequestViewSet(ActionScopedRateThrottleMixin, viewsets.GenericViewSet):
    permission_classes = [IsActiveAccount]
    throttle_scope_prefix = "rgpd"
    throttle_scope_action_map = {
        "me": "rgpd_authenticated_read",
        "create_me": "rgpd_authenticated_write",
    }

    def get_queryset(self):
        return RgpdDataRequest.objects.filter(user=self.request.user).order_by("-submitted_at", "-id")

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        serializer = RgpdDataRequestSerializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @me.mapping.post
    def create_me(self, request):
        serializer = RgpdDataRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data_request = RgpdDataRequest.objects.create(
            user=request.user,
            **serializer.validated_data,
        )
        return Response(
            RgpdDataRequestSerializer(data_request).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    list=extend_schema(
        tags=["RGPD"],
        summary="List my legal documents",
        description="Returns the legal documents uploaded by the authenticated user.",
        responses=RgpdLegalDocumentSerializer(many=True),
    ),
    create=extend_schema(
        tags=["RGPD"],
        summary="Upload legal document",
        description=(
            "Uploads a legal document for the authenticated user using the dedicated "
            "legal-documents storage bucket."
        ),
        request=RgpdLegalDocumentSerializer,
        responses={201: RgpdLegalDocumentSerializer},
    ),
)
class RgpdLegalDocumentViewSet(
    ActionScopedRateThrottleMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = RgpdLegalDocument.objects.select_related("user")
    serializer_class = RgpdLegalDocumentSerializer
    permission_classes = [IsActiveAccount]
    throttle_scope_prefix = "rgpd"
    throttle_scope_action_map = {
        "list": "rgpd_authenticated_read",
        "create": "rgpd_authenticated_write",
    }

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["allowed_content_types"] = settings.LEGAL_DOCUMENT_ALLOWED_CONTENT_TYPES
        context["max_bytes"] = settings.LEGAL_DOCUMENT_MAX_BYTES
        return context


@extend_schema(tags=["Management / RGPD"])
class ManagementRgpdPolicyDocumentViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    serializer_class = ManagementRgpdPolicyDocumentSerializer
    queryset = RgpdPolicyDocument.objects.all().order_by("document_type")
    lookup_field = "uuid"


@extend_schema(tags=["Management / RGPD"])
class ManagementRgpdPolicyVersionViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    queryset = RgpdPolicyVersion.objects.select_related("document").all()
    lookup_field = "uuid"

    def get_serializer_class(self):
        if self.action == "create":
            return ManagementRgpdPolicyVersionCreateSerializer
        return ManagementRgpdPolicyVersionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        output = ManagementRgpdPolicyVersionSerializer(instance)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, uuid=None):
        policy_version = self.get_object()
        policy_version = publish_policy_version(policy_version)
        return Response(
            ManagementRgpdPolicyVersionSerializer(policy_version).data,
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Management / RGPD"])
class ManagementRgpdDataRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]
    queryset = RgpdDataRequest.objects.select_related("user", "resolved_by").all()
    lookup_field = "uuid"

    def get_serializer_class(self):
        if self.action in {"update", "partial_update"}:
            return ManagementRgpdDataRequestUpdateSerializer
        return ManagementRgpdDataRequestSerializer

    def update(self, request, *args, **kwargs):
        data_request = self.get_object()
        serializer = self.get_serializer(data_request, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        data_request = set_data_request_status(
            data_request=data_request,
            status_value=serializer.validated_data["status"],
            resolved_by=request.user,
            resolution_notes=serializer.validated_data.get("resolution_notes"),
        )
        return Response(
            ManagementRgpdDataRequestSerializer(data_request).data,
            status=status.HTTP_200_OK,
        )
