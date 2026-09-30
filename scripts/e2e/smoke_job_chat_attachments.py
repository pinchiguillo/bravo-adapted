#!/usr/bin/env python3
"""
Smoke test: job chat attachments end to end.

Flow:
  1. Register a user
  2. Create and approve an organization
  3. Fetch categories and create an announcement
  4. Create a job
  5. Send a message in the job chat
  6. Upload an attachment with a presigned S3 URL:
       POST /api/assets/initiate-upload/  (kind=job_chat_attachment)
       PUT  <s3_presigned_url>
       POST /api/assets/<asset_id>/complete/
  7. Attach the asset to the message:
       POST /api/jobs/<job_uuid>/messages/<message_uuid>/attachments/
  8. Check the attachment appears in the message list

Usage:
  # Local Docker stack (approves the organization via docker exec)
  python3 scripts/e2e/smoke_job_chat_attachments.py

  # Remote gateway (requires an approved announcement)
  python3 scripts/e2e/smoke_job_chat_attachments.py \
    --url <base_url> --announcement-uuid <uuid>

  # Reuse an existing token (skips registration)
  python3 scripts/e2e/smoke_job_chat_attachments.py --token <jwt> [--url <base_url>]
"""

import argparse
import base64
import subprocess
import sys
import uuid as uuid_lib
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Minimal 1x1 red pixel PNG (valid magic bytes + PIL-verifiable)
# ---------------------------------------------------------------------------
_PNG_1X1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAA"
    "MBAQDJ/pLvAAAAAElFTkSuQmCC"
)
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


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

def register_user(base_url: str) -> str:
    username = f"chat_test_{uuid_lib.uuid4().hex[:8]}"
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
    # Handle both paginated and plain list responses
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


def approve_organization_via_docker(org_uuid: str):
    """Approve an org using docker compose exec (local-only)."""
    cmd = [
        "docker", "compose", "-f", "compose.yml", "exec", "-T", "app",
        "python", "manage.py", "shell", "-c",
        f"from apps.organization.models import Organization; "
        f"o = Organization.objects.get(uuid='{org_uuid}'); "
        f"o.is_validated = True; o.save(update_fields=['is_validated']); "
        f"print('approved')",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or "approved" not in result.stdout:
        fail(
            f"Could not approve organization via docker exec.\n"
            f"For remote gateway, pass --announcement-uuid with a pre-approved announcement.\n"
            f"stderr: {result.stderr[:200]}"
        )
    log(f"Organization approved: {org_uuid}")


def create_announcement(base_url: str, token: str, org_uuid: str, category_uuid: str) -> str:
    uid = uuid_lib.uuid4().hex[:8]
    r = requests.post(
        f"{base_url}/api/organizations/{org_uuid}/announcements/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Test Service {uid}",
            "title": f"Test Announcement {uid}",
            "category": category_uuid,
            "description": "Test description for gateway test.",
            "free_text": "Free text for gateway test.",
            "location": "Madrid",
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Create announcement failed {r.status_code}: {r.text[:300]}")
    announcement_uuid = r.json()["uuid"]
    log(f"Announcement created: {announcement_uuid}")
    return announcement_uuid


def create_job(base_url: str, token: str, announcement_uuid: str) -> str:
    r = requests.post(
        f"{base_url}/api/announcements/{announcement_uuid}/jobs/",
        headers={"Authorization": f"Bearer {token}"},
        json={},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Create job failed {r.status_code}: {r.text[:300]}")
    job_uuid = r.json()["uuid"]
    log(f"Job created: {job_uuid}")
    return job_uuid


def send_message(base_url: str, token: str, job_uuid: str) -> str:
    r = requests.post(
        f"{base_url}/api/jobs/{job_uuid}/send/",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "Test message for attachment gateway test."},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Send message failed {r.status_code}: {r.text[:300]}")
    message_uuid = r.json()["uuid"]
    log(f"Message sent: {message_uuid}")
    return message_uuid


# ---------------------------------------------------------------------------
# Attachment upload flow
# ---------------------------------------------------------------------------

def upload_asset(base_url: str, token: str, file_bytes: bytes, filename: str, content_type: str) -> str:
    """Run the 3-step asset upload and return the confirmed asset_id."""
    headers_auth = {"Authorization": f"Bearer {token}"}

    # Step 1: Initiate
    r = requests.post(
        f"{base_url}/api/assets/initiate-upload/",
        headers=headers_auth,
        json={
            "kind": "job_chat_attachment",
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(file_bytes),
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Initiate upload failed {r.status_code}: {r.text[:300]}")

    data = r.json()
    asset_id       = data["asset_id"]
    upload_url     = data["upload_url"]
    upload_headers = data.get("upload_headers", {})
    complete_url   = data["complete_url"]
    log(f"Asset initiated: {asset_id}")

    # Step 2: PUT to S3
    r_s3 = requests.put(upload_url, data=file_bytes, headers=upload_headers, timeout=30)
    if r_s3.status_code not in (200, 201, 204):
        fail(f"S3 upload failed {r_s3.status_code}: {r_s3.text[:200]}")
    log(f"File uploaded to S3 (HTTP {r_s3.status_code})")

    # Step 3: Complete
    r_complete = requests.post(complete_url, headers=headers_auth, timeout=15)
    if r_complete.status_code not in (200, 201):
        fail(f"Complete upload failed {r_complete.status_code}: {r_complete.text[:300]}")

    asset = r_complete.json()
    assert asset["status"] == "confirmed", f"Expected status=confirmed, got {asset['status']}"
    log(f"Asset confirmed: status={asset['status']}")

    return asset_id


def attach_to_message(base_url: str, token: str, job_uuid: str, message_uuid: str, asset_id: str):
    r = requests.post(
        f"{base_url}/api/jobs/{job_uuid}/messages/{message_uuid}/attachments/",
        headers={"Authorization": f"Bearer {token}"},
        json={"asset_id": asset_id},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        fail(f"Attach to message failed {r.status_code}: {r.text[:300]}")
    attachment = r.json()
    assert str(attachment["asset_id"]) == str(asset_id), (
        f"Returned asset_id mismatch: {attachment['asset_id']} != {asset_id}"
    )
    log(f"Attachment created: uuid={attachment['uuid']}  filename={attachment['filename']}")


def verify_attachment_in_messages(base_url: str, token: str, job_uuid: str, message_uuid: str, asset_id: str):
    r = requests.get(
        f"{base_url}/api/jobs/{job_uuid}/messages/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code != 200:
        fail(f"Get messages failed {r.status_code}: {r.text[:200]}")

    chat = r.json()
    messages = chat.get("messages", [])
    target = next((m for m in messages if str(m["uuid"]) == str(message_uuid)), None)
    if target is None:
        fail(f"Message {message_uuid} not found in chat messages list")

    attachments = target.get("attachments", [])
    if not attachments:
        fail("Message has no attachments in messages list")

    found = next((a for a in attachments if str(a["asset_id"]) == str(asset_id)), None)
    if found is None:
        fail(f"Asset {asset_id} not found in message attachments: {attachments}")

    log(f"Attachment visible in messages list: filename={found['filename']}  size={found['size']}")


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------

def test_attach_unconfirmed_asset(base_url: str, token: str, job_uuid: str, message_uuid: str):
    """Verify that attaching a non-existent asset returns 400."""
    print(f"\n{'─'*60}")
    print("  Validation: attaching unknown asset_id should return 400")
    print(f"{'─'*60}")
    fake_id = str(uuid_lib.uuid4())
    r = requests.post(
        f"{base_url}/api/jobs/{job_uuid}/messages/{message_uuid}/attachments/",
        headers={"Authorization": f"Bearer {token}"},
        json={"asset_id": fake_id},
        timeout=10,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
    log("Unknown asset correctly rejected with 400")


def test_attach_wrong_kind_asset(base_url: str, token: str, job_uuid: str, message_uuid: str):
    """Verify that a confirmed asset with wrong kind is rejected."""
    print(f"\n{'─'*60}")
    print("  Validation: attaching wrong-kind asset should return 400")
    print(f"{'─'*60}")
    # Initiate a generic_upload asset (wrong kind for job_chat)
    r = requests.post(
        f"{base_url}/api/assets/initiate-upload/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "kind": "generic_upload",
            "filename": "wrong.png",
            "content_type": "image/png",
            "size_bytes": len(SAMPLE_PNG),
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        log(f"Could not create generic_upload asset for kind validation test — skipping ({r.status_code})", ok=False)
        return

    data = r.json()
    asset_id   = data["asset_id"]
    upload_url = data["upload_url"]
    upload_headers = data.get("upload_headers", {})
    complete_url = data["complete_url"]

    requests.put(upload_url, data=SAMPLE_PNG, headers=upload_headers, timeout=30)
    requests.post(complete_url, headers={"Authorization": f"Bearer {token}"}, timeout=15)

    # Try to attach the wrong-kind confirmed asset
    r2 = requests.post(
        f"{base_url}/api/jobs/{job_uuid}/messages/{message_uuid}/attachments/",
        headers={"Authorization": f"Bearer {token}"},
        json={"asset_id": asset_id},
        timeout=10,
    )
    assert r2.status_code == 400, f"Expected 400 for wrong kind, got {r2.status_code}: {r2.text[:200]}"
    log("Wrong-kind asset correctly rejected with 400")


def test_unauthenticated_attach(base_url: str, job_uuid: str, message_uuid: str):
    """Verify that unauthenticated attach requests are rejected."""
    print(f"\n{'─'*60}")
    print("  Validation: unauthenticated attach should return 401/403")
    print(f"{'─'*60}")
    r = requests.post(
        f"{base_url}/api/jobs/{job_uuid}/messages/{message_uuid}/attachments/",
        json={"asset_id": str(uuid_lib.uuid4())},
        timeout=10,
    )
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
    log("Unauthenticated attach correctly rejected")


# ---------------------------------------------------------------------------
# Full happy-path scenario
# ---------------------------------------------------------------------------

def setup_announcement(base_url: str, token: str, announcement_uuid: str | None) -> str:
    """
    Return a valid announcement UUID to run tests against.

    If *announcement_uuid* is given, use it directly (remote gateway mode).
    Otherwise create org + announcement (requires BYPASS_ORGANIZATION_VALIDATION=1 in the server env).
    """
    if announcement_uuid:
        log(f"Using provided announcement: {announcement_uuid}")
        return announcement_uuid

    category_uuid = get_category(base_url, token)
    org_uuid = create_organization(base_url, token)
    return create_announcement(base_url, token, org_uuid, category_uuid)


def run_full_scenario(
    base_url: str,
    token: str,
    label: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    announcement_uuid: str,
):
    print(f"\n{'═'*60}")
    print(f"  Scenario: {label}")
    print(f"  file={filename}  size={len(file_bytes)}b  ct={content_type}")
    print(f"{'═'*60}")

    job_uuid = create_job(base_url, token, announcement_uuid)
    message_uuid = send_message(base_url, token, job_uuid)

    # Upload and attach
    asset_id = upload_asset(base_url, token, file_bytes, filename, content_type)
    attach_to_message(base_url, token, job_uuid, message_uuid, asset_id)
    verify_attachment_in_messages(base_url, token, job_uuid, message_uuid, asset_id)

    # Validation tests (reuse same job/message)
    test_attach_unconfirmed_asset(base_url, token, job_uuid, message_uuid)
    test_attach_wrong_kind_asset(base_url, token, job_uuid, message_uuid)
    test_unauthenticated_attach(base_url, job_uuid, message_uuid)

    log(f"Scenario '{label}' passed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="External test for Job Chat attachment flow")
    parser.add_argument("--url", default="http://localhost:24356", help="Base URL of the API (nginx)")
    parser.add_argument("--token", default=None, help="Existing JWT access token (skips registration)")
    parser.add_argument(
        "--announcement-uuid",
        default=None,
        metavar="UUID",
        help=(
            "UUID of a pre-existing approved announcement to run tests against. "
            "Required for remote gateways where docker exec is unavailable. "
            "When omitted, the script creates and approves an org automatically via docker compose exec."
        ),
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 60)
    print(f"  Job Chat Attachment Tests  →  {base_url}")
    print("=" * 60)

    token = args.token or register_user(base_url)
    announcement_uuid = setup_announcement(base_url, token, args.announcement_uuid)

    run_full_scenario(
        base_url, token, "PDF attachment", SAMPLE_PDF, "document.pdf", "application/pdf", announcement_uuid
    )
    run_full_scenario(base_url, token, "PNG attachment", SAMPLE_PNG, "photo.png", "image/png", announcement_uuid)

    print("\n" + "=" * 60)
    log("All job chat attachment tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
