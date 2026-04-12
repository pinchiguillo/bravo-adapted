#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-compose.yml}"
BASE_URL="${LEGAL_DOCS_GATEWAY_URL:-http://nginx}"
PUBLIC_HOST_HEADER="${LEGAL_DOCS_GATEWAY_HOST_HEADER:-localhost:24356}"
EXPECTED_BUCKET="${AWS_LEGAL_DOCUMENTS_BUCKET_NAME:-bravo-media-legal}"
AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

if ! docker compose -f "$COMPOSE_FILE" exec -T localstack \
  awslocal s3api head-bucket --bucket "$EXPECTED_BUCKET" >/dev/null 2>&1; then
  if [ "$AWS_REGION" = "us-east-1" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T localstack \
      awslocal s3api create-bucket --bucket "$EXPECTED_BUCKET" >/dev/null
  else
    docker compose -f "$COMPOSE_FILE" exec -T localstack \
      awslocal s3api create-bucket \
        --bucket "$EXPECTED_BUCKET" \
        --create-bucket-configuration "LocationConstraint=$AWS_REGION" >/dev/null
  fi
fi

docker compose -f "$COMPOSE_FILE" exec -T app env \
  VALIDATION_BASE_URL="$BASE_URL" \
  VALIDATION_HOST_HEADER="$PUBLIC_HOST_HEADER" \
  EXPECTED_LEGAL_BUCKET="$EXPECTED_BUCKET" \
  python - <<'PY'
import json
import os
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = os.environ["VALIDATION_BASE_URL"].rstrip("/") + "/"
HOST_HEADER = os.environ["VALIDATION_HOST_HEADER"]
EXPECTED_BUCKET = os.environ["EXPECTED_LEGAL_BUCKET"]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def build_url(path: str) -> str:
    return urljoin(BASE_URL, path.lstrip("/"))


def send_request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    expected_status: int | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    request_headers = {"Host": HOST_HEADER, **(headers or {})}
    request = Request(build_url(path), data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read()
            status = response.status
            response_headers = dict(response.headers.items())
    except HTTPError as exc:
        payload = exc.read()
        status = exc.code
        response_headers = dict(exc.headers.items())
    except URLError as exc:
        fail(f"Gateway request failed for {path}: {exc}")

    if expected_status is not None and status != expected_status:
        preview = payload.decode("utf-8", errors="replace")
        fail(f"{method} {path} returned {status}, expected {expected_status}. Body: {preview}")

    return status, payload, response_headers


def send_json(method: str, path: str, payload: dict, *, token: str | None = None, expected_status: int) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    _, raw_payload, _ = send_request(
        method,
        path,
        headers=headers,
        body=json.dumps(payload).encode("utf-8"),
        expected_status=expected_status,
    )
    return json.loads(raw_payload.decode("utf-8"))


def send_multipart(
    path: str,
    *,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    content: bytes,
    token: str,
    expected_status: int,
) -> dict:
    boundary = f"codex-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    _, raw_payload, _ = send_request(
        "POST",
        path,
        headers=headers,
        body=b"".join(parts),
        expected_status=expected_status,
    )
    return json.loads(raw_payload.decode("utf-8"))


def parse_bucket_and_key(file_url: str) -> tuple[str, str]:
    parsed = urlparse(file_url)
    path = parsed.path.lstrip("/")
    if path.startswith("s3/"):
        parts = path.split("/", 2)
        if len(parts) < 3:
            fail(f"Could not parse bucket/key from proxied URL: {file_url}")
        return parts[1], parts[2]

    parts = path.split("/", 1)
    if len(parts) < 2:
        fail(f"Could not parse bucket/key from storage URL: {file_url}")
    return parts[0], parts[1]


health_status, _, _ = send_request("GET", "/health/", expected_status=200)
if health_status != 200:
    fail("Gateway healthcheck did not return 200.")

endpoint_status, endpoint_body, _ = send_request("GET", "/api/rgpd/legal-documents/")
if endpoint_status == 404:
    fail("RGPD legal-documents endpoint is not available. Enable RGPD_MODULE_ENABLED=1 and restart the stack.")
if endpoint_status != 401:
    preview = endpoint_body.decode("utf-8", errors="replace")
    fail(f"Unexpected pre-auth status for legal-documents endpoint: {endpoint_status}. Body: {preview}")

user_suffix = uuid.uuid4().hex[:8]
password = "LegalDocs123!"
register_payload = {
    "username": f"legal-docs-{user_suffix}",
    "email": f"legal-docs-{user_suffix}@example.com",
    "password": password,
    "first_name": "Legal",
    "last_name": "Docs",
}
register_response = send_json("POST", "/api/auth/register/", register_payload, expected_status=201)
access_token = register_response.get("access")
if not access_token:
    fail(
        "Register response did not include access token. "
        "AUTH_BYPASS_EMAIL_VERIFICATION must be enabled for this smoke flow."
    )

pdf_bytes = (
    b"%PDF-1.4\n"
    b"1 0 obj<<>>endobj\n"
    b"trailer<<>>\n"
    b"%%EOF\n"
)
upload_response = send_multipart(
    "/api/rgpd/legal-documents/",
    fields={"document_type": "privacy-policy"},
    file_field="file",
    filename="privacy-policy.pdf",
    content_type="application/pdf",
    content=pdf_bytes,
    token=access_token,
    expected_status=201,
)

if upload_response["document_type"] != "privacy-policy":
    fail(f"Unexpected document_type in upload response: {upload_response['document_type']}")

bucket_name, object_key = parse_bucket_and_key(upload_response["file"])
if bucket_name != EXPECTED_BUCKET:
    fail(f"Uploaded document used bucket {bucket_name}, expected {EXPECTED_BUCKET}.")

_, list_payload, _ = send_request(
    "GET",
    "/api/rgpd/legal-documents/",
    headers={"Authorization": f"Bearer {access_token}"},
    expected_status=200,
)
documents = json.loads(list_payload.decode("utf-8"))
results = documents.get("results", [])
if not any(document["uuid"] == upload_response["uuid"] for document in results):
    fail("Uploaded legal document was not returned by the authenticated list endpoint.")

download_status, downloaded_bytes, download_headers = send_request(
    "GET",
    f"/s3/{bucket_name}/{quote(object_key, safe='/')}",
    expected_status=200,
)
if downloaded_bytes != pdf_bytes:
    fail("Downloaded bytes through nginx /s3 gateway do not match the uploaded document.")

content_type = download_headers.get("Content-Type", "")
if "pdf" not in content_type and "octet-stream" not in content_type:
    fail(f"Unexpected content type when downloading legal document: {content_type}")

print("Legal documents flow validated through nginx gateway.")
print(f"Registered user: {register_payload['email']}")
print(f"Uploaded document UUID: {upload_response['uuid']}")
print(f"Bucket: {bucket_name}")
print(f"Object key: {object_key}")
print(f"Gateway download status: {download_status}")
print(f"Gateway content-type: {content_type}")
PY
