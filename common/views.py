from django.http import JsonResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import serializers

from Core.settings import read_project_version


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


@extend_schema(
    summary="Get API version",
    description="Returns the current backend version read from the VERSION file.",
    auth=[],
    responses=inline_serializer(
        name="ApiVersionResponse",
        fields={
            "version": serializers.CharField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def api_version(_request):
    return JsonResponse({"version": read_project_version()})
