from drf_spectacular.utils import OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from common.permissions import IsActiveAccount

from .models import Asset
from .serializers import (
    AssetCompleteUploadSerializer,
    AssetInitiateUploadSerializer,
    AssetSerializer,
    AssetUploadTargetSerializer,
)


@extend_schema(
    tags=["Assets"],
    summary="Initiate file upload",
    description=(
        "Validates file metadata and returns a presigned S3 PUT URL for direct "
        "client-to-S3 upload. After uploading the file to S3, call the *complete_url* "
        "to confirm and finalize the asset."
    ),
    request=AssetInitiateUploadSerializer,
    responses={
        status.HTTP_201_CREATED: AssetUploadTargetSerializer,
    },
)
@api_view(["POST"])
@permission_classes([IsActiveAccount])
def initiate_upload(request):
    serializer = AssetInitiateUploadSerializer(
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    upload_target = serializer.save()
    response_serializer = AssetUploadTargetSerializer(upload_target)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Assets"],
    summary="Complete file upload",
    description=(
        "Confirms that the file has been uploaded to S3. Validates size, content type "
        "and file integrity, then moves it to its final location and marks the asset "
        "as CONFIRMED. No request body required."
    ),
    request=OpenApiTypes.NONE,
    responses={
        status.HTTP_200_OK: AssetSerializer,
        status.HTTP_400_BAD_REQUEST: OpenApiResponse(description="Validation failed."),
        status.HTTP_404_NOT_FOUND: OpenApiResponse(description="Asset not found."),
    },
)
@api_view(["POST"])
@permission_classes([IsActiveAccount])
def complete_upload(request, asset_id):
    try:
        asset = Asset.objects.get(id=asset_id)
    except Asset.DoesNotExist:
        raise NotFound("Asset not found.")

    serializer = AssetCompleteUploadSerializer(
        data={},
        context={"request": request, "asset": asset},
    )
    serializer.is_valid(raise_exception=True)
    confirmed_asset = serializer.save()
    return Response(AssetSerializer(confirmed_asset).data, status=status.HTTP_200_OK)
