#!/usr/bin/env python3
"""
Smoke test: announcement creation with image uploads through the gateway.

Flow (organization owner):
  1. Register a user
  2. Create an organization
  3. Fetch categories
  4. Create an announcement
  5. Upload images with presigned S3 URLs (kind=announcement_image):
       POST /api/organizations/{org}/announcements/{ann}/images/
       PUT  <s3_presigned_url>
       POST <complete_url>  { upload_token }
  6. Check the images appear on the public announcement
  7. Negative cases:
       - PDF rejected (not an image) -> 400
       - content_type does not match the extension -> 400
       - file too large -> 400
       - unauthenticated request -> 401/403

Only image/jpeg and image/png are accepted
(ORGANIZATION_ANNOUNCEMENT_IMAGE_ALLOWED_CONTENT_TYPES). Any other content type,
or a size above ORGANIZATION_ANNOUNCEMENT_IMAGE_MAX_BYTES, returns 400 before a
presigned URL is issued.

Usage:
  # Local Docker stack (requires BYPASS_ORGANIZATION_VALIDATION=1 in .env)
  python3 scripts/e2e/smoke_announcement_workflow.py

  # Remote gateway (requires an approved organization and announcement)
  python3 scripts/e2e/smoke_announcement_workflow.py \
    --url <base_url> --announcement-uuid <uuid> --org-uuid <uuid>

  # Reuse an existing token (skips registration)
  python3 scripts/e2e/smoke_announcement_workflow.py --token <jwt>
"""

import argparse
import base64
import sys
import uuid as uuid_lib
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Minimal valid 1x1 PNG (PIL-verifiable, correct CRC)
# ---------------------------------------------------------------------------
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAA"
    "MBAQDJ/pLvAAAAAElFTkSuQmCC"
)
SAMPLE_PNG = base64.b64decode(_PNG_B64)

# ---------------------------------------------------------------------------
# Minimal valid 1x1 JPEG (PIL-verifiable)
# ---------------------------------------------------------------------------
_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw"
    "8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARCAABAAED"
    "ASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAA"
    "AAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwD"
    "AQACRQMRAD8AJQAB/9k="
)
SAMPLE_JPEG = base64.b64decode(_JPEG_B64)

# ---------------------------------------------------------------------------
# Minimal valid PDF (for rejection tests — NOT an image)
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


# ---------------------------------------------------------------------------
# Auth & setup helpers
# ---------------------------------------------------------------------------

def register_user(base_url: str) -> str:
    username = f"ann_test_{uuid_lib.uuid4().hex[:8]}"
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


def get_category(base_url: str, token: str) -> str:
    r = requests.get(
        f"{base_url}/api/categories/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code != 200:
        fail(f"Get categories failed {r.status_code}: {r.text[:200]}")
    results = r.json()
    items = results.get("results", results) if isinstance(results, dict) else results
    if not items:
        fail("No categories found — seed the database first.")
    category_uuid = items[0]["uuid"]
    log(f"Using category: {category_uuid}")
    return category_uuid


def create_organization(base_url: str, token: str) -> str:
    uid = uuid_lib.uuid4().hex[:8]
    r = requests.post(
        f"{base_url}/api/organizations/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Test Org {uid}",
            "legal_name": f"Test Org {uid} SL",
            "tax_id": f"TEST-{uid}",
            "billing_email": f"billing-{uid}@test.invalid",
            "billing_address": "Calle Test 1",
            "billing_city": "Madrid",
            "billing_country": "ES",
            "billing_postal_code": "28001",
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Create organization failed {r.status_code}: {r.text[:300]}")
    org_uuid = r.json()["uuid"]
    log(f"Organization created: {org_uuid}")
    return org_uuid


def create_announcement(base_url: str, token: str, org_uuid: str, category_uuid: str) -> str:
    uid = uuid_lib.uuid4().hex[:8]
    r = requests.post(
        f"{base_url}/api/organizations/{org_uuid}/announcements/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Test Service {uid}",
            "title": f"Test Announcement {uid}",
            "category": category_uuid,
            "description": "Descripción del servicio para el test.",
            "free_text": "Texto libre para el test.",
            "location": "Madrid",
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Create announcement failed {r.status_code}: {r.text[:300]}")
    announcement_uuid = r.json()["uuid"]
    log(f"Announcement created: {announcement_uuid}")
    return announcement_uuid


# ---------------------------------------------------------------------------
# Announcement image upload (presigned URL flow)
# ---------------------------------------------------------------------------

def upload_announcement_image(
    base_url: str,
    token: str,
    org_uuid: str,
    announcement_uuid: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict:
    """
    Full 3-step presigned upload for an announcement image.
    Returns the confirmed AnnouncementImage representation.
    """
    headers_auth = {"Authorization": f"Bearer {token}"}
    images_url = f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/images/"

    # Step 1: Initiate — returns presigned PUT URL + upload_token
    r = requests.post(
        images_url,
        headers=headers_auth,
        json={"filename": filename, "content_type": content_type, "size_bytes": len(file_bytes)},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Initiate image upload failed {r.status_code}: {r.text[:300]}")

    data = r.json()
    upload_url     = data["upload_url"]
    upload_headers = data.get("upload_headers", {})
    upload_token   = data["upload_token"]
    complete_url   = data["complete_url"]
    log(f"Image upload initiated: {filename}  expires_in={data.get('expires_in')}s")

    # Step 2: PUT to S3
    r_s3 = requests.put(upload_url, data=file_bytes, headers=upload_headers, timeout=30)
    if r_s3.status_code not in (200, 201, 204):
        fail(f"S3 image upload failed {r_s3.status_code}: {r_s3.text[:200]}")
    log(f"Image uploaded to S3 (HTTP {r_s3.status_code})")

    # Step 3: Complete
    r_complete = requests.post(
        complete_url,
        headers=headers_auth,
        json={"upload_token": upload_token},
        timeout=15,
    )
    if r_complete.status_code not in (200, 201):
        fail(f"Complete image upload failed {r_complete.status_code}: {r_complete.text[:300]}")

    image = r_complete.json()
    assert "uuid" in image, f"No uuid in confirmed image response: {image}"
    log(f"Image confirmed: uuid={image['uuid']}  filename={image.get('filename', filename)}")
    return image


def verify_images_on_announcement(
    base_url: str,
    token: str,
    org_uuid: str,
    announcement_uuid: str,
    expected_count: int,
):
    """Verify images appear on the announcement via the org-owner endpoint."""
    r = requests.get(
        f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/images/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code != 200:
        fail(f"Get images failed {r.status_code}: {r.text[:200]}")

    items = r.json()
    images = items.get("results", items) if isinstance(items, dict) else items
    if len(images) < expected_count:
        fail(f"Expected at least {expected_count} image(s), got {len(images)}: {images}")
    log(f"Announcement has {len(images)} image(s) — OK")


# ---------------------------------------------------------------------------
# Validation tests (image-only restrictions)
# ---------------------------------------------------------------------------

def test_pdf_rejected(base_url: str, token: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'─'*60}")
    print("  Validation: PDF must be rejected (not an image)")
    print(f"{'─'*60}")
    r = requests.post(
        f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/images/",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "document.pdf", "content_type": "application/pdf", "size_bytes": len(SAMPLE_PDF)},
        timeout=10,
    )
    assert r.status_code == 400, f"Expected 400 for PDF, got {r.status_code}: {r.text[:200]}"
    log("PDF correctly rejected with 400")


def test_content_type_mismatch(base_url: str, token: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'─'*60}")
    print("  Validation: content_type mismatch with filename must be rejected")
    print(f"{'─'*60}")
    # filename says .pdf but content_type says image/png
    r = requests.post(
        f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/images/",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "photo.pdf", "content_type": "image/png", "size_bytes": len(SAMPLE_PNG)},
        timeout=10,
    )
    assert r.status_code == 400, f"Expected 400 for mismatch, got {r.status_code}: {r.text[:200]}"
    log("content_type/filename mismatch correctly rejected with 400")


def test_oversized_image(base_url: str, token: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'─'*60}")
    print("  Validation: oversized image must be rejected")
    print(f"{'─'*60}")
    r = requests.post(
        f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/images/",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "huge.png", "content_type": "image/png", "size_bytes": 10 * 1024 * 1024},
        timeout=10,
    )
    assert r.status_code == 400, f"Expected 400 for oversized, got {r.status_code}: {r.text[:200]}"
    log("Oversized image correctly rejected with 400")


def test_unauthenticated_upload(base_url: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'─'*60}")
    print("  Validation: unauthenticated image upload must be rejected")
    print(f"{'─'*60}")
    r = requests.post(
        f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/images/",
        json={"filename": "photo.png", "content_type": "image/png", "size_bytes": len(SAMPLE_PNG)},
        timeout=10,
    )
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
    log("Unauthenticated upload correctly rejected")


# ---------------------------------------------------------------------------
# Full workflow
# ---------------------------------------------------------------------------

def run_workflow(base_url: str, token: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'═'*60}")
    print("  Workflow: upload PNG + JPEG images to announcement")
    print(f"{'═'*60}")

    # Upload PNG
    upload_announcement_image(
        base_url, token, org_uuid, announcement_uuid,
        SAMPLE_PNG, "banner.png", "image/png",
    )

    # Upload JPEG
    upload_announcement_image(
        base_url, token, org_uuid, announcement_uuid,
        SAMPLE_JPEG, "cover.jpg", "image/jpeg",
    )

    # Verify both images are attached
    verify_images_on_announcement(base_url, token, org_uuid, announcement_uuid, expected_count=2)

    # Validation: image-only restrictions
    test_pdf_rejected(base_url, token, org_uuid, announcement_uuid)
    test_content_type_mismatch(base_url, token, org_uuid, announcement_uuid)
    test_oversized_image(base_url, token, org_uuid, announcement_uuid)
    test_unauthenticated_upload(base_url, org_uuid, announcement_uuid)

    log("Full announcement image workflow passed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="External test for announcement image workflow")
    parser.add_argument("--url", default="http://localhost:24356", help="Base URL of the API (nginx)")
    parser.add_argument("--token", default=None, help="Existing JWT token (skips registration)")
    parser.add_argument(
        "--org-uuid",
        default=None,
        metavar="UUID",
        help="UUID of a pre-existing approved organization (remote gateway mode).",
    )
    parser.add_argument(
        "--announcement-uuid",
        default=None,
        metavar="UUID",
        help=(
            "UUID of a pre-existing announcement to run image tests against. "
            "Required for remote gateways. When omitted, a new org+announcement is created "
            "(requires BYPASS_ORGANIZATION_VALIDATION=1 on the server)."
        ),
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 60)
    print(f"  Announcement Workflow Tests  →  {base_url}")
    print("=" * 60)

    token = args.token or register_user(base_url)

    if args.announcement_uuid and args.org_uuid:
        org_uuid          = args.org_uuid
        announcement_uuid = args.announcement_uuid
        log(f"Using provided org: {org_uuid}")
        log(f"Using provided announcement: {announcement_uuid}")
    else:
        category_uuid     = get_category(base_url, token)
        org_uuid          = args.org_uuid or create_organization(base_url, token)
        announcement_uuid = args.announcement_uuid or create_announcement(
            base_url, token, org_uuid, category_uuid
        )

    run_workflow(base_url, token, org_uuid, announcement_uuid)

    print("\n" + "=" * 60)
    log("All announcement workflow tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
