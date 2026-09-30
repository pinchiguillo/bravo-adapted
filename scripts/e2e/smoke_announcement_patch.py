#!/usr/bin/env python3
"""
Smoke test: PATCH an organization announcement through the nginx gateway.

Flow: authenticate -> resolve or create an organization and announcement ->
PATCH the title -> PATCH nested subservices -> check the owner listing
reflects both changes (and that nothing returns a 500).

Usage:
  python3 scripts/e2e/smoke_announcement_patch.py [--url http://localhost:24356]
  python3 scripts/e2e/smoke_announcement_patch.py --url <base_url> \
    --token <jwt> --org-uuid <uuid> --announcement-uuid <uuid>
"""

import argparse
import sys
import uuid as uuid_lib
from datetime import date, datetime, timedelta

import requests

from smoke_announcement_workflow import (
    create_announcement,
    create_organization,
    get_category,
    register_user,
)


def log(msg, ok=True):
    icon = "✅" if ok else "❌"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {icon} {msg}")


def fail(msg):
    log(msg, ok=False)
    raise SystemExit(1)


def request_json(method: str, url: str, *, token: str | None = None, payload=None, timeout: int = 15):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(method, url, headers=headers, json=payload, timeout=timeout)
    body = None
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return response, body


def ensure_bootstrap_resources(base_url: str, token: str, org_uuid: str | None, announcement_uuid: str | None):
    if org_uuid and announcement_uuid:
        log(f"Using provided organization: {org_uuid}")
        log(f"Using provided announcement: {announcement_uuid}")
        return org_uuid, announcement_uuid

    category_uuid = get_category(base_url, token)
    org_uuid = org_uuid or create_organization(base_url, token)
    try:
        announcement_uuid = announcement_uuid or create_announcement(base_url, token, org_uuid, category_uuid)
    except SystemExit:
        fail(
            "Bootstrap failed while creating the announcement. "
            "Provide --org-uuid and --announcement-uuid for an existing approved resource, "
            "or enable BYPASS_ORGANIZATION_VALIDATION=1 on the target server."
        )
    return org_uuid, announcement_uuid


def patch_announcement(base_url: str, token: str, org_uuid: str, announcement_uuid: str, payload: dict):
    url = f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/"
    response, body = request_json("PATCH", url, token=token, payload=payload)
    preview = str(body)[:400]
    log(f"PATCH {url} -> {response.status_code} payload={payload}")
    print(f"     response: {preview}")
    return response, body


def fetch_owner_announcement(base_url: str, token: str, org_uuid: str, announcement_uuid: str):
    url = f"{base_url}/api/organizations/{org_uuid}/announcements/"
    response, body = request_json("GET", url, token=token)
    if response.status_code != 200:
        fail(f"Owner announcement list failed {response.status_code}: {str(body)[:300]}")
    items = body.get("results", body) if isinstance(body, dict) else body
    for item in items:
        if item.get("uuid") == announcement_uuid:
            return item
    fail(f"Announcement {announcement_uuid} not found in owner listing")


def get_service_catalog_uuid(base_url: str):
    response, body = request_json("GET", f"{base_url}/api/services/")
    if response.status_code != 200:
        fail(f"Service catalog lookup failed {response.status_code}: {str(body)[:300]}")
    items = body.get("results", body) if isinstance(body, dict) else body
    if not items:
        fail("No service catalog entries found.")
    return items[0]["uuid"]


def test_patch_title(base_url: str, token: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'═' * 60}")
    print("  Validation: PATCH simple fields should succeed")
    print(f"{'═' * 60}")
    expected_title = f"Gateway PATCH Title {uuid_lib.uuid4().hex[:8]}"
    response, body = patch_announcement(
        base_url,
        token,
        org_uuid,
        announcement_uuid,
        {"title": expected_title, "description": "Descripcion actualizada desde gateway test."},
    )
    if response.status_code != 200:
        fail(f"Simple PATCH failed {response.status_code}: {str(body)[:300]}")
    if body.get("title") != expected_title:
        fail(f"PATCH response did not reflect updated title: {body}")

    owner_item = fetch_owner_announcement(base_url, token, org_uuid, announcement_uuid)
    if owner_item.get("title") != expected_title:
        fail(f"Owner listing did not reflect updated title: {owner_item}")
    log("Simple PATCH updated the announcement title")


def test_patch_subservices(base_url: str, token: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'═' * 60}")
    print("  Validation: PATCH nested subservices should not 500")
    print(f"{'═' * 60}")
    tomorrow = date.today() + timedelta(days=1)
    service_catalog_uuid = get_service_catalog_uuid(base_url)
    payload = {
        "subservices": [
            {
                "service_catalog": service_catalog_uuid,
                "name": f"Gateway Nested {uuid_lib.uuid4().hex[:6]}",
                "description": "Subservice updated through PATCH gateway test.",
                "prices": [
                    {
                        "amount": "79.99",
                        "currency": "eur",
                        "charging_type": "per_project",
                        "effective_from": tomorrow.isoformat(),
                        "effective_to": tomorrow.isoformat(),
                    }
                ],
            }
        ]
    }

    response, body = patch_announcement(base_url, token, org_uuid, announcement_uuid, payload)
    if response.status_code != 200:
        fail(f"Nested subservices PATCH failed {response.status_code}: {str(body)[:300]}")

    patched_services = body.get("services", [])
    if len(patched_services) != 1:
        fail(f"Expected exactly 1 grouped service after nested PATCH, got: {patched_services}")
    patched_subservices = patched_services[0].get("subservices", [])
    if len(patched_subservices) != 1:
        fail(f"Expected exactly 1 subservice after nested PATCH, got: {patched_subservices}")
    patched_subservice = patched_subservices[0]
    if patched_subservice.get("name") != payload["subservices"][0]["name"]:
        fail(f"Nested subservice name mismatch after PATCH: {patched_subservice}")
    prices = patched_subservice.get("service_prices", [])
    if len(prices) != 1 or prices[0].get("amount") != "79.99":
        fail(f"Nested subservice prices mismatch after PATCH: {patched_subservice}")
    log("Nested subservices PATCH succeeded without server error")


def test_unauthenticated_patch_rejected(base_url: str, org_uuid: str, announcement_uuid: str):
    print(f"\n{'═' * 60}")
    print("  Validation: unauthenticated PATCH should be rejected")
    print(f"{'═' * 60}")
    url = f"{base_url}/api/organizations/{org_uuid}/announcements/{announcement_uuid}/"
    response, body = request_json("PATCH", url, payload={"title": "Should not work"})
    if response.status_code not in (401, 403):
        fail(f"Expected 401/403 for unauthenticated PATCH, got {response.status_code}: {body}")
    log(f"Unauthenticated PATCH rejected with {response.status_code}")


def main():
    parser = argparse.ArgumentParser(description="Gateway PATCH test for organization announcements")
    parser.add_argument("--url", default="http://localhost:24356", help="Base URL of the API gateway")
    parser.add_argument("--token", default=None, help="Existing JWT access token (skips registration)")
    parser.add_argument("--org-uuid", default=None, metavar="UUID", help="Existing organization UUID")
    parser.add_argument(
        "--announcement-uuid",
        default=None,
        metavar="UUID",
        help="Existing announcement UUID",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 60)
    print(f"  Announcement PATCH Gateway Test  →  {base_url}")
    print("=" * 60)

    token = args.token or register_user(base_url)
    org_uuid, announcement_uuid = ensure_bootstrap_resources(
        base_url,
        token,
        args.org_uuid,
        args.announcement_uuid,
    )

    test_patch_title(base_url, token, org_uuid, announcement_uuid)
    test_patch_subservices(base_url, token, org_uuid, announcement_uuid)
    test_unauthenticated_patch_rejected(base_url, org_uuid, announcement_uuid)

    print("\n" + "=" * 60)
    log("Announcement PATCH gateway tests passed")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
