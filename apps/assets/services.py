"""
Generic S3 upload services.

This module centralizes all S3 presigned-upload logic so that multiple
Django apps (organization, job_chat, …) can reuse it without duplication.
"""

import io
import os
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from botocore.exceptions import ClientError
from django.conf import settings
from django.core import signing
from django.http import HttpRequest
from django.utils import timezone
from django.utils.encoding import filepath_to_uri

from common.exceptions import DomainError

try:
    from PIL import Image, UnidentifiedImageError

    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False


# Magic-byte signatures for content types we know how to validate
_MAGIC_BYTES: dict[str, bytes] = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "application/pdf": b"%PDF",
}


class UploadRejected(DomainError):
    """The uploaded object does not match what the client declared."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="upload_rejected", field="file")


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def build_public_media_url(
    file_name: str, *, request: HttpRequest | None = None, signed_url: str | None = None
) -> str | None:
    """URL a client should use to reach a stored object.

    Presigned URLs are returned unchanged: SigV4 signs the host and path, so
    rebuilding them on another base (a CDN, another addressing style) breaks
    the signature. The exception is development, where MEDIA_PUBLIC_BASE_URL
    points at the nginx proxy in front of LocalStack, which does not verify
    signatures. Unsigned objects are served from MEDIA_URL.
    """
    if not file_name:
        return None
    if signed_url and not settings.MEDIA_PUBLIC_BASE_URL:
        return signed_url

    url = f"{settings.MEDIA_URL.rstrip('/')}/{filepath_to_uri(file_name).lstrip('/')}"
    if signed_url:
        query = urlsplit(signed_url).query
        if query:
            url = f"{url}?{query}"

    if request is None or not url.startswith("/"):
        return url
    return str(request.build_absolute_uri(url))


# ---------------------------------------------------------------------------
# Token helpers (Django signing)
# ---------------------------------------------------------------------------


def build_upload_token(payload: dict[str, Any], *, salt: str) -> str:
    return signing.dumps(payload, salt=salt)


def load_upload_token(token: str, *, salt: str, max_age: int) -> dict[str, Any]:
    payload: dict[str, Any] = signing.loads(token, salt=salt, max_age=max_age)
    return payload


# ---------------------------------------------------------------------------
# S3 key builders
# ---------------------------------------------------------------------------


def build_asset_key(kind: str, asset_id: str, filename: str) -> str:
    """
    Build the final S3 key for an asset.

    Pattern: assets/{kind}/{yyyy}/{mm}/{dd}/{asset_id}/{uuid}.{ext}
    """
    ext = os.path.splitext(filename)[1].lower()
    now = timezone.now()
    return f"assets/{kind}/{now:%Y/%m/%d}/{asset_id}/{uuid.uuid4().hex}{ext}"


def build_pending_asset_key(kind: str, asset_id: str, filename: str) -> str:
    """
    Build the temporary (pending) S3 key used during direct upload.

    Pattern: assets-pending/{kind}/{yyyy}/{mm}/{dd}/{asset_id}/{uuid}.{ext}
    """
    ext = os.path.splitext(filename)[1].lower()
    now = timezone.now()
    return f"assets-pending/{kind}/{now:%Y/%m/%d}/{asset_id}/{uuid.uuid4().hex}{ext}"


# ---------------------------------------------------------------------------
# S3 operations
# ---------------------------------------------------------------------------


def generate_presigned_upload_url(storage: Any, *, key: str, content_type: str, ttl_seconds: int) -> str:
    """Generate a presigned PUT URL for direct client-to-S3 upload."""
    client = storage.connection.meta.client
    url: str = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": storage.bucket_name,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=ttl_seconds,
        HttpMethod="PUT",
    )
    return url


def validate_file_magic_bytes(file_bytes: bytes, content_type: str) -> None:
    """
    Validate magic bytes for known content types.

    For image/* types with PIL available, also runs PIL.verify().
    For unknown types, no byte-level check is performed.

    Raises UploadRejected on failure.
    """
    magic = _MAGIC_BYTES.get(content_type)
    if magic and not file_bytes[: len(magic)].startswith(magic):
        raise UploadRejected(f"Uploaded file is not a valid {content_type} file.")

    if content_type.startswith("image/") and _PIL_AVAILABLE:
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise UploadRejected("Uploaded file is not a valid image.") from exc


def move_pending_to_confirmed(
    storage: Any,
    *,
    pending_key: str,
    final_key: str,
    content_type: str,
    expected_size: int,
) -> None:
    """
    Validate an object in S3 and move it from pending to final location.

    Steps:
      1. HeadObject to verify existence, size and content-type.
      2. GetObject + validate magic bytes.
      3. CopyObject pending → final.
      4. DeleteObject pending.

    Raises UploadRejected on any inconsistency; the pending file is deleted
    before raising.
    """
    client = storage.connection.meta.client

    try:
        head = client.head_object(Bucket=storage.bucket_name, Key=pending_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code", "") in {"404", "NoSuchKey", "NotFound"}:
            raise UploadRejected("Uploaded file was not found in storage.") from exc
        raise

    if int(head.get("ContentLength", 0)) != int(expected_size):
        client.delete_object(Bucket=storage.bucket_name, Key=pending_key)
        raise UploadRejected("Uploaded file size does not match the declared size.")

    if str(head.get("ContentType", "")).lower() != str(content_type).lower():
        client.delete_object(Bucket=storage.bucket_name, Key=pending_key)
        raise UploadRejected("Uploaded file content type does not match the declared content type.")

    obj = client.get_object(Bucket=storage.bucket_name, Key=pending_key)
    file_bytes = obj["Body"].read()

    try:
        validate_file_magic_bytes(file_bytes, content_type)
    except UploadRejected:
        client.delete_object(Bucket=storage.bucket_name, Key=pending_key)
        raise

    client.copy_object(
        Bucket=storage.bucket_name,
        CopySource={"Bucket": storage.bucket_name, "Key": pending_key},
        Key=final_key,
        ContentType=content_type,
        MetadataDirective="REPLACE",
    )
    client.delete_object(Bucket=storage.bucket_name, Key=pending_key)


def cleanup_expired_pending_files(storage: Any, prefix: str, max_age_seconds: int) -> None:
    """Delete objects under *prefix* in S3 that are older than *max_age_seconds*."""
    if not hasattr(storage, "bucket_name") or not hasattr(storage, "connection"):
        return
    if max_age_seconds <= 0:
        return

    cutoff = timezone.now() - timedelta(seconds=max_age_seconds)
    client = storage.connection.meta.client
    paginator = client.get_paginator("list_objects_v2")
    pending_keys = []

    for page in paginator.paginate(Bucket=storage.bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            last_modified = obj.get("LastModified")
            if last_modified is None:
                continue
            if timezone.is_naive(last_modified):
                last_modified = timezone.make_aware(last_modified)
            if last_modified <= cutoff:
                pending_keys.append({"Key": obj["Key"]})

    while pending_keys:
        chunk, pending_keys = pending_keys[:1000], pending_keys[1000:]
        client.delete_objects(
            Bucket=storage.bucket_name,
            Delete={"Objects": chunk, "Quiet": True},
        )


def delete_s3_file(storage: Any, key: str) -> None:
    """Delete a single object from S3. No-op if storage is not S3 or key is empty."""
    if not key or not hasattr(storage, "bucket_name") or not hasattr(storage, "connection"):
        return
    storage.connection.meta.client.delete_object(Bucket=storage.bucket_name, Key=key)
