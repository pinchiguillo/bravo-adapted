#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-compose.yml}"
GATEWAY_URL="${PLAN_TIER_GATEWAY_URL:-http://localhost:24356}"

docker compose -f "$COMPOSE_FILE" exec -T app python manage.py shell -c '
import uuid

from django.contrib.auth import get_user_model

from apps.organization.models import Organization, OrganizationPricing, PlanTierCatalog

user_model = get_user_model()
user, _ = user_model.objects.get_or_create(
    username="gateway-plan-tier-owner",
    defaults={
        "email": "gateway-plan-tier-owner@example.com",
        "password": "unused-password",
    },
)
if not user.email:
    user.email = "gateway-plan-tier-owner@example.com"
    user.save(update_fields=["email"])

organization, _ = Organization.objects.get_or_create(
    user=user,
    defaults={
        "name": "Gateway Pricing Org",
        "legal_name": "Gateway Pricing Org SL",
        "tax_id": "GW-PLAN-001",
        "billing_email": "billing@gateway-pricing-org.example.com",
        "billing_address": "Gateway Street 1",
        "billing_city": "Madrid",
        "billing_country": "ES",
        "billing_postal_code": "28001",
        "is_approved": True,
    },
)
if not organization.is_approved:
    organization.is_approved = True
    organization.save(update_fields=["is_approved"])

for key, name, description, sort_order in [
    ("default", "Default", "Tier base para organizaciones con configuracion estandar.", 10),
    ("premium", "Premium", "Tier con condiciones comerciales avanzadas.", 20),
    ("pro", "Pro", "Tier profesional para organizaciones con mas volumen.", 30),
    ("ultra", "Ultra", "Tier de maximas prestaciones y personalizacion.", 40),
]:
    PlanTierCatalog.objects.update_or_create(
        key=key,
        defaults={
            "name": name,
            "description": description,
            "sort_order": sort_order,
        },
    )

premium_tier = PlanTierCatalog.objects.get(key="premium")
pricing, created = OrganizationPricing.objects.get_or_create(
    organization=organization,
    defaults={
        "uuid": uuid.uuid4(),
        "plan_tier": premium_tier,
        "monthly_price": "49.99",
        "commission_rate": "12.50",
        "currency": "EUR",
    },
)
if not created and pricing.plan_tier_id != premium_tier.id:
    pricing.plan_tier = premium_tier
    pricing.save(update_fields=["plan_tier"])

print(organization.uuid)
' >/tmp/plan_tier_gateway_setup.txt

ORGANIZATION_UUID="$(tail -n 1 /tmp/plan_tier_gateway_setup.txt | tr -d '\r\n')"

PLAN_TIERS_BODY="$(curl -fsS "$GATEWAY_URL/api/plan-tiers/")"
ORGANIZATION_BODY="$(curl -fsS "$GATEWAY_URL/api/organizations/$ORGANIZATION_UUID/")"

case "$PLAN_TIERS_BODY" in
  *'"key":"default"'* ) ;;
  * ) echo "ERROR: default tier not found in public catalog response" >&2; exit 1 ;;
esac
case "$PLAN_TIERS_BODY" in
  *'"key":"premium"'* ) ;;
  * ) echo "ERROR: premium tier not found in public catalog response" >&2; exit 1 ;;
esac
case "$PLAN_TIERS_BODY" in
  *'"key":"pro"'* ) ;;
  * ) echo "ERROR: pro tier not found in public catalog response" >&2; exit 1 ;;
esac
case "$PLAN_TIERS_BODY" in
  *'"key":"ultra"'* ) ;;
  * ) echo "ERROR: ultra tier not found in public catalog response" >&2; exit 1 ;;
esac
case "$ORGANIZATION_BODY" in
  *'"plan_tier":{"uuid":'*'"key":"premium"'* ) ;;
  * ) echo "ERROR: organization response does not expose premium plan_tier" >&2; echo "$ORGANIZATION_BODY" >&2; exit 1 ;;
esac

echo "Public gateway validation OK"
echo "Gateway URL: $GATEWAY_URL"
echo "Organization UUID: $ORGANIZATION_UUID"
