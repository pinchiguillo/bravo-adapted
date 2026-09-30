#!/usr/bin/env python3
"""
Smoke test: create an announcement with nested subservices and prices.

Flow: register a user -> create an organization -> fetch the service catalog ->
POST a nested announcement payload -> check nested services and prices in the
response and in the public detail endpoint.

Usage:
  python3 scripts/e2e/smoke_new_announcement_creation_workflow.py [--url <base_url>]
"""

import argparse
import sys
import uuid as uuid_lib
from datetime import date, datetime, timedelta

import requests


def log(msg, ok=True):
    icon = "✅" if ok else "❌"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {icon} {msg}")


def fail(msg):
    log(msg, ok=False)
    sys.exit(1)


def register_user(base_url: str) -> str:
    username = f"announcement_test_{uuid_lib.uuid4().hex[:8]}"
    email = f"{username}@test.invalid"
    password = "TestPassword123!"
    response = requests.post(
        f"{base_url}/api/auth/register/",
        json={
            "username": username,
            "email": email,
            "password": password,
            "password_confirm": password,
        },
        timeout=20,
    )
    if response.status_code not in (200, 201):
        fail(f"Register failed {response.status_code}: {response.text[:300]}")
    token = response.json().get("access")
    if not token:
        fail(f"No access token in register response: {response.text[:300]}")
    log(f"Registered user: {email}")
    return token


def create_organization(base_url: str, token: str) -> str:
    suffix = uuid_lib.uuid4().hex[:8]
    response = requests.post(
        f"{base_url}/api/organizations/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Nested Announcement Org {suffix}",
            "legal_name": f"Nested Announcement Org {suffix} SL",
            "tax_id": f"NESTED-{suffix}",
            "billing_email": f"billing-{suffix}@test.invalid",
            "billing_address": "Calle Gateway 1",
            "billing_city": "Madrid",
            "billing_country": "ES",
            "billing_postal_code": "28001",
        },
        timeout=20,
    )
    if response.status_code not in (200, 201):
        fail(f"Create organization failed {response.status_code}: {response.text[:300]}")
    organization_uuid = response.json()["uuid"]
    log(f"Organization created: {organization_uuid}")
    return organization_uuid


def fetch_service_catalogs(base_url: str) -> list[dict]:
    response = requests.get(f"{base_url}/api/services/", timeout=20)
    if response.status_code != 200:
        fail(f"Fetch services failed {response.status_code}: {response.text[:300]}")
    payload = response.json()
    items = payload.get("results", payload) if isinstance(payload, dict) else payload
    if len(items) < 2:
        fail("At least two service catalog entries are required for this test.")
    return items


def create_nested_announcement(base_url: str, token: str, organization_uuid: str, service_catalogs: list[dict]) -> dict:
    today = date.today()
    next_month = today + timedelta(days=30)
    first_service = service_catalogs[0]
    second_service = next(
        (service for service in service_catalogs[1:] if service["uuid"] != first_service["uuid"]),
        None,
    )
    if second_service is None:
        fail("Could not find two distinct service catalog entries.")

    payload = {
        "category": first_service["category"]["uuid"],
        "name": "Reforma integral con tarifas",
        "location": "Madrid Centro",
        "title": "Alta completa de announcement",
        "status": "active",
        "description": "Prueba de creacion anidada de announcement con precios.",
        "free_text": "Incluye subservicios y tabla de precios en un unico POST.",
        "subservices": [
            {
                "service_catalog": first_service["uuid"],
                "name": "Visita tecnica inicial",
                "description": "Evaluacion in situ y toma de requisitos.",
                "prices": [
                    {
                        "amount": "90.00",
                        "currency": "EUR",
                        "charging_type": "per_project",
                        "effective_from": today.isoformat(),
                        "effective_to": next_month.isoformat(),
                    }
                ],
            },
            {
                "service_catalog": second_service["uuid"],
                "name": "Ejecucion principal",
                "description": "Implementacion del servicio solicitado.",
                "prices": [
                    {
                        "amount": "120.00",
                        "currency": "EUR",
                        "charging_type": "per_day",
                        "effective_from": today.isoformat(),
                        "effective_to": next_month.isoformat(),
                    },
                    {
                        "amount": "45.00",
                        "currency": "EUR",
                        "charging_type": "per_hour",
                        "effective_from": (today + timedelta(days=1)).isoformat(),
                        "effective_to": next_month.isoformat(),
                    },
                ],
            },
        ],
    }

    response = requests.post(
        f"{base_url}/api/organizations/{organization_uuid}/announcements/",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=20,
    )
    if response.status_code not in (200, 201):
        fail(f"Create nested announcement failed {response.status_code}: {response.text[:500]}")
    data = response.json()
    log(f"Announcement created with nested payload: {data['uuid']}")
    return data


def assert_nested_response_shape(announcement: dict):
    assert announcement["status"] == "active", announcement
    assert announcement["name"] == "Reforma integral con tarifas", announcement
    assert announcement["title"] == "Alta completa de announcement", announcement
    assert announcement["lowest_price"] == "45.00", announcement

    services = announcement.get("services", [])
    assert len(services) == 2, services

    subservices = [
        subservice
        for service in services
        for subservice in service.get("subservices", [])
    ]
    assert len(subservices) == 2, subservices

    names = {subservice["name"] for subservice in subservices}
    assert names == {"Visita tecnica inicial", "Ejecucion principal"}, names

    prices_by_subservice = {
        subservice["name"]: subservice.get("service_prices", [])
        for subservice in subservices
    }
    assert len(prices_by_subservice["Visita tecnica inicial"]) == 1, prices_by_subservice
    assert len(prices_by_subservice["Ejecucion principal"]) == 2, prices_by_subservice

    amount_map = {
        subservice_name: {price["amount"] for price in prices}
        for subservice_name, prices in prices_by_subservice.items()
    }
    assert amount_map["Visita tecnica inicial"] == {"90.00"}, amount_map
    assert amount_map["Ejecucion principal"] == {"120.00", "45.00"}, amount_map

    log("Nested services and prices returned in create response")


def verify_public_detail(base_url: str, announcement_uuid: str):
    response = requests.get(f"{base_url}/api/announcements/{announcement_uuid}/", timeout=20)
    if response.status_code != 200:
        fail(f"Public detail failed {response.status_code}: {response.text[:400]}")
    data = response.json()
    assert_nested_response_shape(data)
    log("Public announcement detail exposes nested subservices and prices")


def main():
    parser = argparse.ArgumentParser(
        description="External test for nested announcement creation workflow"
    )
    parser.add_argument("--url", default="http://localhost:24356", help="Base URL of the API gateway")
    parser.add_argument("--token", default=None, help="Existing JWT access token (skips registration)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 60)
    print(f"  New Announcement Creation Workflow  →  {base_url}")
    print("=" * 60)

    token = args.token or register_user(base_url)
    organization_uuid = create_organization(base_url, token)
    service_catalogs = fetch_service_catalogs(base_url)
    created = create_nested_announcement(base_url, token, organization_uuid, service_catalogs)

    assert_nested_response_shape(created)
    verify_public_detail(base_url, created["uuid"])

    print("\n" + "=" * 60)
    log("Nested announcement creation workflow passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
