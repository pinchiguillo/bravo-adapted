#!/usr/bin/env python3
"""
Smoke test: generic asset upload with presigned S3 URLs.

Endpoints:
  POST /api/assets/initiate-upload/
  PUT  <s3_presigned_url>
  POST /api/assets/<asset_id>/complete/

Usage:
  # Local Docker stack
  python3 scripts/e2e/smoke_asset_upload.py

  # Remote gateway
  python3 scripts/e2e/smoke_asset_upload.py --url <base_url>

  # Reuse an existing token
  python3 scripts/e2e/smoke_asset_upload.py --token <jwt> [--url <base_url>]
"""

import argparse
import base64
import sys
import uuid as uuid_lib
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Minimal 1x1 red pixel PNG (valid magic bytes + PIL-verifiable)
# ---------------------------------------------------------------------------
_PNG_1X1_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
SAMPLE_PNG = base64.b64decode(_PNG_1X1_B64)

# ---------------------------------------------------------------------------
# Minimal valid PDF
# ---------------------------------------------------------------------------
SAMPLE_PDF = (
    b"%PDF-1.0\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f\n"
    b"0000000009 00000 n\n"
    b"0000000058 00000 n\n"
    b"0000000115 00000 n\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n190\n%%EOF\n"
)


def log(msg, ok=True):
    icon = "✅" if ok else "❌"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {icon} {msg}")


def fail(msg):
    log(msg, ok=False)
    sys.exit(1)


def register_user(base_url: str) -> str:
    username = f"asset_test_{uuid_lib.uuid4().hex[:8]}"
    email = f"{username}@test.invalid"
    password = "TestPassword123!"
    r = requests.post(
        f"{base_url}/api/auth/register/",
        json={"username": username, "email": email, "password": password, "password_confirm": password},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Register failed {r.status_code}: {r.text[:200]}")
    token = r.json().get("access")
    if not token:
        fail(f"No access token in register response: {r.text[:200]}")
    log(f"Registered user: {email}")
    return token


def test_asset_upload(base_url: str, token: str, kind: str, file_bytes: bytes, filename: str, content_type: str):
    headers_auth = {"Authorization": f"Bearer {token}"}
    print(f"\n{'─' * 60}")
    print(f"  kind={kind}  file={filename}  size={len(file_bytes)}b")
    print(f"{'─' * 60}")

    # Step 1: Initiate upload
    print("  [1/3] Initiating upload...")
    r = requests.post(
        f"{base_url}/api/assets/initiate-upload/",
        headers=headers_auth,
        json={"kind": kind, "filename": filename, "content_type": content_type, "size_bytes": len(file_bytes)},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Initiate upload failed {r.status_code}: {r.text[:300]}")

    data = r.json()
    asset_id = data["asset_id"]
    upload_url = data["upload_url"]
    upload_method = data.get("upload_method", "PUT")
    upload_headers = data.get("upload_headers", {})
    complete_url = data["complete_url"]
    expires_in = data["expires_in"]
    log(f"Asset created: {asset_id}  (expires_in={expires_in}s)")

    assert upload_method == "PUT", f"Expected PUT, got {upload_method}"

    # Step 2: Upload to S3
    print("  [2/3] Uploading file to S3...")
    r_s3 = requests.put(upload_url, data=file_bytes, headers=upload_headers, timeout=30)
    if r_s3.status_code not in (200, 201, 204):
        fail(f"S3 upload failed {r_s3.status_code}: {r_s3.text[:200]}")
    log(f"File uploaded to S3  (HTTP {r_s3.status_code})")

    # Step 3: Complete upload
    print("  [3/3] Confirming upload...")
    r_complete = requests.post(
        complete_url,
        headers=headers_auth,
        timeout=15,
    )
    if r_complete.status_code not in (200, 201):
        fail(f"Complete upload failed {r_complete.status_code}: {r_complete.text[:300]}")

    asset = r_complete.json()
    assert asset["status"] == "confirmed", f"Expected status=confirmed, got {asset['status']}"
    assert asset["kind"] == kind, f"Expected kind={kind}, got {asset['kind']}"
    log(f"Asset confirmed: status={asset['status']}  kind={asset['kind']}")

    return asset_id


def test_invalid_kind(base_url: str, token: str):
    """Verify that invalid kind is rejected."""
    print(f"\n{'─' * 60}")
    print("  Validation: invalid kind should return 400")
    print(f"{'─' * 60}")
    r = requests.post(
        f"{base_url}/api/assets/initiate-upload/",
        headers={"Authorization": f"Bearer {token}"},
        json={"kind": "not_a_valid_kind", "filename": "x.png", "content_type": "image/png", "size_bytes": 100},
        timeout=10,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
    log("Invalid kind correctly rejected with 400")


def test_oversized_file(base_url: str, token: str):
    """Verify that oversized size_bytes is rejected."""
    print(f"\n{'─' * 60}")
    print("  Validation: oversized file should return 400")
    print(f"{'─' * 60}")
    r = requests.post(
        f"{base_url}/api/assets/initiate-upload/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "kind": "announcement_image",
            "filename": "huge.png",
            "content_type": "image/png",
            "size_bytes": 100 * 1024 * 1024,  # 100 MB, way over limit
        },
        timeout=10,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
    log("Oversized file correctly rejected with 400")


def test_unauthenticated(base_url: str):
    """Verify that unauthenticated requests are rejected."""
    print(f"\n{'─' * 60}")
    print("  Validation: unauthenticated request should return 401")
    print(f"{'─' * 60}")
    r = requests.post(
        f"{base_url}/api/assets/initiate-upload/",
        json={"kind": "generic_upload", "filename": "x.png", "content_type": "image/png", "size_bytes": 100},
        timeout=10,
    )
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
    log("Unauthenticated request correctly rejected")


def main():
    parser = argparse.ArgumentParser(description="External test for Asset upload flow")
    parser.add_argument("--url", default="http://localhost:24356", help="Base URL of the API (nginx)")
    parser.add_argument("--token", default=None, help="Existing JWT access token (skips registration)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 60)
    print(f"  Asset Upload Tests  →  {base_url}")
    print("=" * 60)

    token = args.token or register_user(base_url)

    # Happy paths
    test_asset_upload(base_url, token, "generic_upload", SAMPLE_PNG, "test.png", "image/png")
    test_asset_upload(base_url, token, "job_chat_attachment", SAMPLE_PDF, "doc.pdf", "application/pdf")
    test_asset_upload(base_url, token, "job_chat_attachment", SAMPLE_PNG, "photo.png", "image/png")

    # Validation errors
    test_invalid_kind(base_url, token)
    test_oversized_file(base_url, token)
    test_unauthenticated(base_url)

    print("\n" + "=" * 60)
    log("All asset upload tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
