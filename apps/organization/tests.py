import base64
import io
import uuid
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from .middleware import AnnouncementViewCountMiddleware
from .models import (
    AllowedCity,
    Announcement,
    AnnouncementImage,
    AnnouncementReview,
    Category,
    Organization,
    OrganizationPricing,
    PlanTierCatalog,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)
from .permissions import IsOrganizationResourceOwner
from .views import OrganizationViewSet


class OrganizationApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="org-owner",
            email="org-owner@example.com",
            password="testpass123",
        )
        self.other_owner = user_model.objects.create_user(
            username="other-owner",
            email="other-owner@example.com",
            password="testpass123",
        )
        self.admin_user = user_model.objects.create_user(
            username="org-admin",
            email="org-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.user_without_organization = user_model.objects.create_user(
            username="no-org-user",
            email="no-org-user@example.com",
            password="testpass123",
        )

        self.organization = Organization.objects.create(
            user=self.owner,
            name="Acme",
            legal_name="Acme SL",
            tax_id="A123",
            billing_email="billing@acme.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            is_approved=True,
        )
        self.other_organization = Organization.objects.create(
            user=self.other_owner,
            name="Beta",
            legal_name="Beta SL",
            tax_id="B456",
            billing_email="billing@beta.com",
            billing_address="Second 2",
            billing_city="Barcelona",
            billing_country="ES",
            billing_postal_code="08001",
            is_approved=True,
        )
        self.category = Category.objects.create(
            name="Home Services",
            description="Servicios para el hogar",
        )
        self.allowed_city = AllowedCity.objects.create(name="Madrid")
        self.other_allowed_city = AllowedCity.objects.create(name="Barcelona")
        self.other_category = Category.objects.create(
            name="Pet Services",
            description="Servicios para mascotas",
        )
        self.default_plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="test-org-default",
            defaults={
                "name": "Test Org Default",
                "description": "Plan base",
                "sort_order": 10,
            },
        )
        self.premium_plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="test-org-premium",
            defaults={
                "name": "Test Org Premium",
                "description": "Plan premium",
                "sort_order": 20,
            },
        )
        self.owner_service_catalog = ServiceCatalog.objects.create(
            category=self.category,
            name="Owner Plan",
            description="Owner service",
        )
        self.other_service_catalog = ServiceCatalog.objects.create(
            category=self.other_category,
            name="Other Plan",
            description="Other service",
        )
        self.owner_organization_job_uuid = uuid.uuid4()
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Weekend Cleaning",
            location="Madrid",
            announcement="Promo de limpieza",
            status=Announcement.Status.ACTIVE,
            description="Servicio de limpieza a domicilio",
            free_text="Disponible sabados",
            latitude="40.4168",
            longitude="-3.7038",
        )
        self.owner_subservice = Subservice.objects.create(
            announcement=self.announcement,
            service_catalog=self.owner_service_catalog,
            name="Owner Subservice",
            description="Owner subservice",
        )
        self.owner_service_price = ServicePrice.objects.create(
            subservice=self.owner_subservice,
            amount="49.99",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        self.organization_pricing = OrganizationPricing.objects.create(
            organization=self.organization,
            plan_tier=self.premium_plan_tier,
            monthly_price="49.99",
            commission_rate="12.50",
        )
        self.announcement_review = AnnouncementReview.objects.create(
            announcement=self.announcement,
            content="Muy recomendable",
        )
        self.closed_announcement = Announcement.objects.create(
            organization=self.other_organization,
            category=self.other_category,
            name="Dog Walking",
            location="Barcelona",
            announcement="Paseos diarios",
            status=Announcement.Status.CLOSED,
            description="Paseador con experiencia",
            free_text="Disponible entre semana",
        )
        self.other_subservice = Subservice.objects.create(
            announcement=self.closed_announcement,
            service_catalog=self.other_service_catalog,
            name="Other Subservice",
            description="Other subservice",
        )

    def test_organization_retrieve_is_public_by_uuid(self):
        response = self.client.get(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "uuid": str(self.organization.uuid),
                "name": self.organization.name,
                "verification_level": 0,
                "is_approved": True,
                "plan_tier": {
                    "uuid": str(self.premium_plan_tier.uuid),
                    "key": self.premium_plan_tier.key,
                    "name": self.premium_plan_tier.name,
                    "description": self.premium_plan_tier.description,
                },
                "rating": None,
            },
        )

    def test_organization_public_retrieve_omits_sensitive_fields(self):
        response = self.client.get(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("legal_name", response.data)
        self.assertNotIn("tax_id", response.data)
        self.assertNotIn("billing_email", response.data)
        self.assertNotIn("billing_address", response.data)
        self.assertNotIn("billing_city", response.data)
        self.assertNotIn("billing_postal_code", response.data)

    def test_organization_me_returns_private_fields_for_owner(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(reverse("organization-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.organization.uuid))
        self.assertEqual(response.data["legal_name"], self.organization.legal_name)
        self.assertTrue(response.data["is_approved"])
        self.assertEqual(response.data["tax_id"], self.organization.tax_id)
        self.assertEqual(response.data["billing_email"], self.organization.billing_email)
        self.assertEqual(response.data["verification_level"], self.organization.verification_level)
        self.assertEqual(response.data["plan_tier"]["key"], self.premium_plan_tier.key)
        self.assertIsNone(response.data["rating"])

    def test_public_retrieve_hides_unapproved_organization_for_anonymous_user(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])

        response = self.client.get(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_retrieve_hides_unapproved_organization_for_non_owner_user(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])
        self.client.force_authenticate(user=self.other_owner)

        response = self.client.get(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_retrieve_unapproved_organization_by_uuid(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.organization.uuid))
        self.assertFalse(response.data["is_approved"])

    def test_organization_root_get_is_not_available_as_list(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("organization-list"))

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_category_list_is_public_and_read_only(self):
        response = self.client.get(reverse("organization-category-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(set(item.keys()), {"uuid", "name"})
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertGreaterEqual(response.data["count"], 2)
        self.assertTrue({str(self.category.uuid), str(self.other_category.uuid)}.issubset(returned_uuids))

    def test_allowed_city_list_is_public_and_read_only(self):
        response = self.client.get(reverse("organization-allowed-city-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(set(item.keys()), {"uuid", "name"})
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertGreaterEqual(response.data["count"], 2)
        self.assertTrue(
            {str(self.allowed_city.uuid), str(self.other_allowed_city.uuid)}.issubset(returned_uuids)
        )

    def test_allowed_city_detail_route_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-allowed-city-detail", kwargs={"uuid": self.allowed_city.uuid})

    def test_category_detail_route_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-category-detail", kwargs={"uuid": self.category.uuid})

    def test_plan_tier_list_is_public_and_read_only(self):
        response = self.client.get(reverse("organization-plan-tier-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(set(item.keys()), {"uuid", "key", "name", "description"})
        returned_keys = {item["key"] for item in response.data["results"]}
        self.assertTrue({"default", "premium"}.issubset(returned_keys))

    def test_service_catalog_list_is_public(self):
        response = self.client.get(reverse("service-catalog-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(set(item.keys()), {"uuid", "name", "category"})
            self.assertEqual(set(item["category"].keys()), {"uuid", "name"})
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            returned_uuids,
            {str(self.owner_service_catalog.uuid), str(self.other_service_catalog.uuid)},
        )
        owner_item = next(
            item
            for item in response.data["results"]
            if item["uuid"] == str(self.owner_service_catalog.uuid)
        )
        self.assertEqual(
            owner_item["category"],
            {
                "uuid": str(self.category.uuid),
                "name": self.category.name,
            },
        )

    def test_service_catalog_list_is_paginated(self):
        ServiceCatalog.objects.create(
            category=self.category,
            name="Second Category Service",
            description="Second category service",
        )

        response = self.client.get(reverse("service-catalog-list"), {"page_size": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])

    def test_service_catalog_list_returns_fixed_catalog_without_duplicates_from_organization_services(
        self,
    ):
        hidden_owner = get_user_model().objects.create_user(
            username="hidden-category-owner",
            email="hidden-category-owner@example.com",
            password="testpass123",
        )
        hidden_organization = Organization.objects.create(
            user=hidden_owner,
            name="Hidden Org",
            legal_name="Hidden Org SL",
            tax_id="H123",
            billing_email="billing@hidden.example.com",
            billing_address="Hidden 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            is_approved=False,
        )
        hidden_announcement = Announcement.objects.create(
            organization=hidden_organization,
            category=self.category,
            name="Hidden announcement",
            location="Madrid",
            announcement="Hidden announcement",
            status=Announcement.Status.ACTIVE,
            description="Should not duplicate catalog",
            free_text="Hidden",
        )
        Subservice.objects.create(
            announcement=hidden_announcement,
            service_catalog=self.owner_service_catalog,
            name="Hidden Subservice",
            description="Should not duplicate catalog",
        )

        response = self.client.get(reverse("service-catalog-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertEqual(
            returned_uuids,
            {str(self.owner_service_catalog.uuid), str(self.other_service_catalog.uuid)},
        )

    def test_service_catalog_detail_route_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("service-catalog-detail", kwargs={"pk": self.owner_service_catalog.uuid})

    def test_organization_admin_endpoint_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-admin-list")

    def test_organization_search_endpoint_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-search")

    def test_authenticated_user_can_create_organization(self):
        self.client.force_authenticate(user=self.user_without_organization)

        response = self.client.post(
            reverse("organization-list"),
            {
                "name": "Gamma",
                "legal_name": "Gamma SL",
                "tax_id": "G789",
                "billing_email": "billing@gamma.com",
                "billing_address": "Third 3",
                "billing_city": "Valencia",
                "billing_country": "ES",
                "billing_postal_code": "46001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Organization.objects.get(user=self.user_without_organization)
        self.assertEqual(response.data["uuid"], str(created.uuid))
        self.assertEqual(response.data["name"], "Gamma")

    def test_me_endpoint_returns_authenticated_user_organization(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(reverse("organization-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.organization.uuid))
        self.assertEqual(response.data["legal_name"], self.organization.legal_name)
        self.assertTrue(response.data["is_approved"])

    def test_me_endpoint_can_update_authenticated_user_organization(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            reverse("organization-me"),
            {"name": "Acme Via User Endpoint"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Acme Via User Endpoint")

    def test_user_endpoint_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-user")

    def test_user_with_organization_cannot_create_second_organization(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse("organization-list"),
            {
                "name": "Acme 2",
                "legal_name": "Acme 2 SL",
                "tax_id": "A999",
                "billing_email": "billing2@acme.com",
                "billing_address": "Main 2",
                "billing_city": "Madrid",
                "billing_country": "ES",
                "billing_postal_code": "28002",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Authenticated user already has an organization.")

    def test_patch_is_not_available_for_organization_detail(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid}),
            {"name": "Acme Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Acme")

    def test_put_is_not_available_for_organization_detail(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.put(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid}),
            {
                "name": "Acme Replaced",
                "legal_name": "Acme Replace SL",
                "tax_id": "A999",
                "billing_email": "replace@acme.com",
                "billing_address": "Main 99",
                "billing_city": "Madrid",
                "billing_country": "ES",
                "billing_postal_code": "28099",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Acme")

    def test_delete_is_not_available_for_organization_detail(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.delete(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Organization.objects.filter(uuid=self.organization.uuid).exists())

    def test_suspended_owner_cannot_update_organization_via_me(self):
        self.owner.status = self.owner.Status.SUSPENDED
        self.owner.save(update_fields=["status"])
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            reverse("organization-me"),
            {"name": "Blocked Update"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Acme")

    def test_owner_can_delete_organization_via_me(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.delete(reverse("organization-me"))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Organization.objects.filter(uuid=self.organization.uuid).exists())

    def test_organization_resource_owner_permission_allows_owner_organization_resource(self):
        request = RequestFactory().patch("/")
        request.user = self.owner

        allowed = IsOrganizationResourceOwner().has_object_permission(
            request,
            None,
            self.organization,
        )

        self.assertTrue(allowed)

    def test_organization_resource_owner_permission_allows_owner_subservice_resource(self):
        request = RequestFactory().patch("/")
        request.user = self.owner

        allowed = IsOrganizationResourceOwner().has_object_permission(
            request,
            None,
            self.owner_subservice,
        )

        self.assertTrue(allowed)

    def test_organization_resource_owner_permission_allows_owner_announcement_resource(self):
        request = RequestFactory().patch("/")
        request.user = self.owner

        allowed = IsOrganizationResourceOwner().has_object_permission(
            request,
            None,
            self.announcement,
        )

        self.assertTrue(allowed)

    def test_organization_resource_owner_permission_allows_owner_service_price_resource(self):
        request = RequestFactory().patch("/")
        request.user = self.owner

        allowed = IsOrganizationResourceOwner().has_object_permission(
            request,
            None,
            self.owner_service_price,
        )

        self.assertTrue(allowed)

    def test_organization_resource_owner_permission_denies_foreign_resource(self):
        request = RequestFactory().patch("/")
        request.user = self.other_owner

        allowed = IsOrganizationResourceOwner().has_object_permission(
            request,
            None,
            self.owner_subservice,
        )

        self.assertFalse(allowed)

    def test_organization_resource_owner_permission_denies_anonymous_user(self):
        request = RequestFactory().patch("/")
        request.user = AnonymousUser()

        allowed = IsOrganizationResourceOwner().has_object_permission(
            request,
            None,
            self.organization,
        )

        self.assertFalse(allowed)

    def test_private_job_routes_do_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-job-list", kwargs={"organization_uuid": self.organization.uuid})

        with self.assertRaises(NoReverseMatch):
            reverse(
                "organization-job-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job_uuid,
                },
            )

    def test_private_nested_subservice_routes_exist(self):
        self.assertEqual(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                },
            ),
            (
                f"/api/announcements/{self.announcement.uuid}/subservices/"
            ),
        )
        self.assertEqual(
            reverse(
                "organization-subservice-detail",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            ),
            f"/api/announcements/{self.announcement.uuid}/subservices/{self.owner_subservice.uuid}/",
        )
        self.assertEqual(
            reverse(
                "organization-service-price-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            ),
            f"/api/announcements/{self.announcement.uuid}/subservices/{self.owner_subservice.uuid}/prices/",
        )
        self.assertEqual(
            reverse(
                "organization-service-price-detail",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                    "price_uuid": self.owner_service_price.uuid,
                },
            ),
            (
                f"/api/announcements/{self.announcement.uuid}/subservices/{self.owner_subservice.uuid}"
                f"/prices/{self.owner_service_price.uuid}/"
            ),
        )

    def test_public_nested_subservice_and_price_endpoints_exist(self):
        self.assertEqual(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                },
            ),
            f"/api/announcements/{self.announcement.uuid}/subservices/",
        )
        self.assertEqual(
            reverse(
                "organization-service-price-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            ),
            f"/api/announcements/{self.announcement.uuid}/subservices/{self.owner_subservice.uuid}/prices/",
        )

    def test_organization_public_retrieve_is_throttled(self):
        cache.clear()

        class OrganizationPublicReadTestThrottle(SimpleRateThrottle):
            scope = "organization_public_read_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        with patch.object(OrganizationViewSet, "throttle_classes", [OrganizationPublicReadTestThrottle]):
            first_response = self.client.get(
                reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
            )
            second_response = self.client.get(
                reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
            )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_announcement_list_requires_authentication(self):
        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_create_subservice_for_owned_announcement(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                },
            ),
            {
                "announcement": str(self.announcement.uuid),
                "service_catalog": str(self.owner_service_catalog.uuid),
                "name": "Window Cleaning",
                "description": "Interior and exterior windows",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data["announcement"]), str(self.announcement.uuid))
        self.assertEqual(
            response.data["service_catalog"],
            {
                "uuid": str(self.owner_service_catalog.uuid),
                "name": self.owner_service_catalog.name,
            },
        )
        self.assertEqual(response.data["name"], "Window Cleaning")

    def test_owner_can_create_service_price_for_owned_subservice(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-service-price-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            ),
            {
                "subservice": str(self.owner_subservice.uuid),
                "amount": "79.99",
                "currency": "EUR",
                "charging_type": ServicePrice.ChargingType.PER_PROJECT,
                "effective_from": "2026-04-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["subservice"], str(self.owner_subservice.uuid))
        self.assertEqual(response.data["amount"], "79.99")

    def test_public_announcement_list_allows_anonymous_requests_without_filters(self):
        response = self.client.get(reverse("public-announcement-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.announcement.uuid))
        self.assertNotIn("review", response.data["results"][0])

    def test_public_announcement_list_hides_unapproved_organization_announcements(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])

        response = self.client.get(reverse("public-announcement-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    @override_settings(BYPASS_ORGANIZATION_VALIDATION=True)
    def test_bypass_organization_validation_exposes_unapproved_organization_as_approved(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])

        response = self.client.get(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_approved"])

    def test_public_announcement_list_filters_across_all_organizations(self):
        matching = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Electric Repairs",
            location="Sevilla",
            announcement="Urgencias electricas",
            status=Announcement.Status.ACTIVE,
            description="Servicio 24 horas",
            free_text="guardias nocturnas",
        )
        Announcement.objects.create(
            organization=self.organization,
            category=self.other_category,
            name="Dog Walking",
            location="Madrid",
            announcement="Paseos diarios",
            status=Announcement.Status.ACTIVE,
            description="Mascotas felices",
            free_text="turno de manana",
        )

        response = self.client.get(
            reverse("public-announcement-list"),
            {"search": "guardias"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(matching.uuid))

    def test_public_announcement_list_filters_by_category_and_search_text(self):
        matching = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Home Repairs",
            location="Madrid Norte",
            announcement="Reparaciones urgentes",
            status=Announcement.Status.ACTIVE,
            description="Servicio para averias domesticas",
            free_text="guardias nocturnas",
        )
        non_matching_category = Announcement.objects.create(
            organization=self.other_organization,
            category=self.other_category,
            name="Pet Grooming",
            location="Madrid",
            announcement="Peluqueria canina",
            status=Announcement.Status.ACTIVE,
            description="Corte y bano",
            free_text="guardias nocturnas",
        )
        non_matching_text = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Home Painting",
            location="Madrid",
            announcement="Pintura interior",
            status=Announcement.Status.ACTIVE,
            description="Pintores profesionales",
            free_text="trabajos programados",
        )

        response = self.client.get(
            reverse("public-announcement-list"),
            {"category": str(self.category.uuid), "search": "guardias"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(matching.uuid))
        self.assertNotEqual(response.data["results"][0]["uuid"], str(non_matching_category.uuid))
        self.assertNotEqual(response.data["results"][0]["uuid"], str(non_matching_text.uuid))

    def test_public_announcement_list_filters_by_categories_param(self):
        matching = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Home Repairs",
            location="Madrid Norte",
            announcement="Reparaciones urgentes",
            status=Announcement.Status.ACTIVE,
            description="Servicio para averias domesticas",
            free_text="guardias nocturnas",
        )
        Announcement.objects.create(
            organization=self.other_organization,
            category=self.other_category,
            name="Pet Grooming",
            location="Madrid",
            announcement="Peluqueria canina",
            status=Announcement.Status.ACTIVE,
            description="Corte y bano",
            free_text="guardias nocturnas",
        )

        response = self.client.get(
            reverse("public-announcement-list"),
            {"categories": [str(self.category.uuid)]},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {item["uuid"] for item in response.data["results"]},
            {str(self.announcement.uuid), str(matching.uuid)},
        )

    def test_public_announcement_list_filters_by_service(self):
        matching = Announcement.objects.create(
            organization=self.other_organization,
            category=self.other_category,
            name="Pet Grooming",
            location="Madrid",
            announcement="Peluqueria canina",
            status=Announcement.Status.ACTIVE,
            description="Corte y bano",
            free_text="Guardias fines de semana",
        )
        Subservice.objects.create(
            announcement=matching,
            service_catalog=self.other_service_catalog,
            name="Pet Grooming Plus",
            description="Corte y bano",
        )
        non_matching = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Home Repairs",
            location="Madrid Norte",
            announcement="Reparaciones urgentes",
            status=Announcement.Status.ACTIVE,
            description="Servicio para averias domesticas",
            free_text="Guardias nocturnas",
        )
        Subservice.objects.create(
            announcement=non_matching,
            service_catalog=self.owner_service_catalog,
            name="Home Repairs Base",
            description="Servicio para averias domesticas",
        )

        response = self.client.get(
            reverse("public-announcement-list"),
            {"service": str(self.other_service_catalog.uuid)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(matching.uuid))
        self.assertNotEqual(response.data["results"][0]["uuid"], str(non_matching.uuid))

    def test_public_announcement_list_filters_by_uuid_organization_and_coordinates(self):
        matching = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Exact Match",
            location="Bilbao",
            announcement="Servicio concreto",
            status=Announcement.Status.ACTIVE,
            description="Con coordenadas",
            free_text="Match total",
            latitude="43.2630",
            longitude="-2.9350",
        )
        Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="No Coordinates",
            location="Bilbao",
            announcement="Servicio sin mapa",
            status=Announcement.Status.ACTIVE,
            description="Sin coordenadas",
            free_text="No match",
        )

        response = self.client.get(
            reverse("public-announcement-list"),
            {
                "uuid": str(matching.uuid),
                "organization": str(self.other_organization.uuid),
                "has_coordinates": "true",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(matching.uuid))

    def test_public_announcement_list_filters_by_specific_text_fields(self):
        matching = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Urgent Plumber",
            location="Valencia Centro",
            announcement="Fontaneria inmediata",
            status=Announcement.Status.ACTIVE,
            description="Reparacion de fugas",
            free_text="Disponible hoy",
        )
        Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Urgent Electrician",
            location="Valencia Centro",
            announcement="Electricidad inmediata",
            status=Announcement.Status.ACTIVE,
            description="Reparacion de fugas",
            free_text="Disponible hoy",
        )

        response = self.client.get(
            reverse("public-announcement-list"),
            {
                "name": "plumber",
                "location": "valencia",
                "title": "fontaneria",
                "description": "fugas",
                "free_text": "hoy",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(matching.uuid))

    def test_public_announcement_list_rejects_invalid_has_coordinates_value(self):
        response = self.client.get(
            reverse("public-announcement-list"),
            {"has_coordinates": "maybe"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(response.data["has_coordinates"]),
            "Use a boolean value: true or false.",
        )

    def test_public_announcement_list_returns_most_recent_announcements_first(self):
        older = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Older Announcement",
            location="Barcelona",
            announcement="Servicio antiguo",
            status=Announcement.Status.ACTIVE,
            description="Publicado antes",
            free_text="orden de prueba",
        )
        newest = Announcement.objects.create(
            organization=self.other_organization,
            category=self.category,
            name="Newest Announcement",
            location="Sevilla",
            announcement="Servicio reciente",
            status=Announcement.Status.ACTIVE,
            description="Publicado despues",
            free_text="orden de prueba",
        )

        response = self.client.get(reverse("public-announcement-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["uuid"] for item in response.data["results"]],
            [str(newest.uuid), str(older.uuid), str(self.announcement.uuid)],
        )

    def test_public_announcement_detail_is_available_by_uuid(self):
        response = self.client.get(
            reverse(
                "public-announcement-detail",
                kwargs={"uuid": self.announcement.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.announcement.uuid))
        self.assertEqual(response.data["organization"], str(self.organization.uuid))
        self.assertEqual(
            response.data["category"],
            {
                "uuid": str(self.category.uuid),
                "name": self.category.name,
            },
        )
        self.assertEqual(response.data["lowest_price"], "49.99")
        self.assertEqual(response.data["services"][0]["uuid"], str(self.owner_service_catalog.uuid))
        self.assertEqual(
            response.data["services"][0]["category"],
            {
                "uuid": str(self.category.uuid),
                "name": self.category.name,
            },
        )
        self.assertEqual(
            response.data["services"][0]["subservices"][0]["uuid"],
            str(self.owner_subservice.uuid),
        )
        self.assertEqual(
            response.data["services"][0]["subservices"][0]["service_catalog"],
            {
                "uuid": str(self.owner_service_catalog.uuid),
                "name": self.owner_service_catalog.name,
            },
        )
        self.assertEqual(
            response.data["services"][0]["subservices"][0]["service_prices"][0]["uuid"],
            str(self.owner_service_price.uuid),
        )

    def test_public_announcement_detail_hides_unapproved_organization(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])

        response = self.client.get(
            reverse(
                "public-announcement-detail",
                kwargs={"uuid": self.announcement.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_subservice_list_is_available_by_organization_and_announcement(self):
        response = self.client.get(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.owner_subservice.uuid))

    def test_public_subservice_retrieve_is_available_by_nested_uuids(self):
        response = self.client.get(
            reverse(
                "organization-subservice-detail",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.owner_subservice.uuid))
        self.assertEqual(str(response.data["announcement"]), str(self.announcement.uuid))
        self.assertEqual(
            response.data["service_catalog"],
            {
                "uuid": str(self.owner_service_catalog.uuid),
                "name": self.owner_service_catalog.name,
            },
        )

    def test_public_service_price_list_is_available_by_nested_uuids(self):
        response = self.client.get(
            reverse(
                "organization-service-price-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.owner_service_price.uuid))

    def test_public_service_price_retrieve_is_available_by_nested_uuids(self):
        response = self.client.get(
            reverse(
                "organization-service-price-detail",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                    "price_uuid": self.owner_service_price.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.owner_service_price.uuid))
        self.assertEqual(response.data["subservice"], str(self.owner_subservice.uuid))

    def test_public_subservices_and_prices_hide_unapproved_organization(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])

        subservice_response = self.client.get(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                },
            )
        )
        price_response = self.client.get(
            reverse(
                "organization-service-price-list",
                kwargs={
                    "announcement_uuid": self.announcement.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            )
        )

        self.assertEqual(subservice_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(price_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_announcement_route_is_not_available_under_organizations_prefix(self):
        response = self.client.get("/api/organizations/announcements/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_announcement_list_filters_by_categories(self):
        self.client.force_authenticate(user=self.owner)
        second_category = Category.objects.create(name="Garden", description="Jardineria")
        second_announcement = Announcement.objects.create(
            organization=self.organization,
            category=second_category,
            name="Garden Maintenance",
            location="Madrid Norte",
            announcement="Puesta a punto de jardin",
            status=Announcement.Status.ACTIVE,
            description="Mantenimiento semanal",
            free_text="Incluye poda",
        )

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {"categories": [str(self.category.uuid)]},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.announcement.uuid))
        self.assertNotEqual(response.data["results"][0]["uuid"], str(second_announcement.uuid))

    def test_announcement_list_filters_by_single_category_param(self):
        self.client.force_authenticate(user=self.owner)
        second_category = Category.objects.create(name="Garden", description="Jardineria")
        Announcement.objects.create(
            organization=self.organization,
            category=second_category,
            name="Garden Maintenance",
            location="Madrid Norte",
            announcement="Puesta a punto de jardin",
            status=Announcement.Status.ACTIVE,
            description="Mantenimiento semanal",
            free_text="Incluye poda",
        )

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {"category": str(self.category.uuid)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.announcement.uuid))

    def test_announcement_list_filters_by_service(self):
        self.client.force_authenticate(user=self.owner)
        second_announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Deep Cleaning",
            location="Madrid Sur",
            announcement="Limpieza intensiva",
            status=Announcement.Status.ACTIVE,
            description="Incluye cocina y banos",
            free_text="Disponible domingos",
        )
        Subservice.objects.create(
            announcement=second_announcement,
            service_catalog=self.other_service_catalog,
            name="Deep Cleaning Extra",
            description="Incluye cocina y banos",
        )

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {"service": str(self.owner_service_catalog.uuid)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.announcement.uuid))
        self.assertNotEqual(response.data["results"][0]["uuid"], str(second_announcement.uuid))

    def test_announcement_list_filters_by_status_uuid_and_coordinates(self):
        self.client.force_authenticate(user=self.owner)
        matching = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Draft Plumbing",
            location="Madrid Oeste",
            announcement="Pendiente de publicar",
            status=Announcement.Status.SUSPENDED,
            description="Suspendido por revision",
            free_text="Sin mapa",
        )
        Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Mapped Plumbing",
            location="Madrid Oeste",
            announcement="Activo con mapa",
            status=Announcement.Status.SUSPENDED,
            description="Suspendido con mapa",
            free_text="Con mapa",
            latitude="40.5000",
            longitude="-3.7000",
        )

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "uuid": str(matching.uuid),
                "status": Announcement.Status.SUSPENDED,
                "has_coordinates": "false",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(matching.uuid))

    def test_announcement_list_filters_by_specific_text_fields(self):
        self.client.force_authenticate(user=self.owner)
        matching = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Weekend Gardening",
            location="Alcobendas",
            announcement="Jardineria de mantenimiento",
            status=Announcement.Status.ACTIVE,
            description="Cesped y poda",
            free_text="Disponible domingos",
        )
        Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Weekend Painting",
            location="Alcobendas",
            announcement="Pintura de mantenimiento",
            status=Announcement.Status.ACTIVE,
            description="Cesped y poda",
            free_text="Disponible domingos",
        )

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "name": "gardening",
                "location": "alcob",
                "title": "jardineria",
                "description": "poda",
                "free_text": "domingos",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(matching.uuid))

    def test_announcement_list_rejects_invalid_has_coordinates_value(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {"has_coordinates": "invalid"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(response.data["has_coordinates"]),
            "Use a boolean value: true or false.",
        )

    def test_announcement_list_filters_by_search_text(self):
        self.client.force_authenticate(user=self.owner)
        Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Electric Repairs",
            location="Barcelona",
            announcement="Revision electrica",
            status=Announcement.Status.ACTIVE,
            description="Servicio tecnico general",
            free_text="Disponible entre semana",
        )

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {"search": "sabados"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.announcement.uuid))

    def test_announcement_list_combines_category_and_search_filters(self):
        self.client.force_authenticate(user=self.owner)
        garden_category = Category.objects.create(name="Garden Plus", description="Exterior")
        Announcement.objects.create(
            organization=self.organization,
            category=garden_category,
            name="Garden Saturdays",
            location="Madrid",
            announcement="Jardineria express",
            status=Announcement.Status.ACTIVE,
            description="Cuidado del cesped",
            free_text="Disponible sabados",
        )

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "categories": [str(self.category.uuid)],
                "search": "sabados",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.announcement.uuid))

    def test_organization_owner_can_create_announcement(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "category": str(self.category.uuid),
                "name": "Emergency Plumbing",
                "location": "Madrid Centro",
                "title": "Atencion 24 horas",
                "status": Announcement.Status.ACTIVE,
                "description": "Servicio urgente",
                "free_text": "Atendemos festivos",
                "latitude": "40.4167",
                "longitude": "-3.7033",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Announcement.objects.get(uuid=response.data["uuid"])
        self.assertEqual(created.organization, self.organization)
        self.assertEqual(response.data["organization"], str(self.organization.uuid))
        self.assertEqual(
            response.data["category"],
            {
                "uuid": str(self.category.uuid),
                "name": self.category.name,
            },
        )
        self.assertIsNone(response.data["lowest_price"])
        self.assertEqual(response.data["title"], "Atencion 24 horas")
        self.assertNotIn("announcement", response.data)
        self.assertEqual(response.data["services"], [])
        self.assertEqual(response.data["view_count"], 0)
        self.assertNotIn("review", response.data)

    def test_organization_owner_can_create_announcement_with_nested_subservices(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "category": str(self.category.uuid),
                "name": "Pack completo de reformas",
                "location": "Madrid Centro",
                "title": "Servicio integral",
                "status": Announcement.Status.ACTIVE,
                "description": "Incluye varias lineas de servicio",
                "free_text": "Disponible bajo cita previa",
                "subservices": [
                    {
                        "service_catalog": str(self.owner_service_catalog.uuid),
                        "name": "Visita tecnica",
                        "description": "Diagnostico inicial",
                    },
                    {
                        "service_catalog": str(self.other_service_catalog.uuid),
                        "name": "Acabado final",
                        "description": "Cierre del servicio",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Announcement.objects.get(uuid=response.data["uuid"])
        self.assertEqual(created.subservices.count(), 2)
        self.assertEqual(
            set(created.subservices.values_list("name", flat=True)),
            {"Visita tecnica", "Acabado final"},
        )
        self.assertEqual(len(response.data["services"]), 2)
        self.assertEqual(
            {service["name"] for service in response.data["services"]},
            {self.owner_service_catalog.name, self.other_service_catalog.name},
        )
        self.assertEqual(
            {
                subservice["name"]
                for service in response.data["services"]
                for subservice in service["subservices"]
            },
            {"Visita tecnica", "Acabado final"},
        )

    def test_public_announcement_detail_returns_null_lowest_price_when_no_prices_exist(self):
        announcement_without_prices = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="No Price Announcement",
            location="Madrid",
            announcement="Sin tarifas publicadas",
            status=Announcement.Status.ACTIVE,
            description="Servicio sin precios",
            free_text="Consulta presupuesto",
        )

        response = self.client.get(
            reverse(
                "public-announcement-detail",
                kwargs={"uuid": announcement_without_prices.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["lowest_price"])

    def test_unapproved_organization_cannot_create_announcement(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "category": str(self.category.uuid),
                "name": "Emergency Plumbing",
                "location": "Madrid Centro",
                "title": "Atencion 24 horas",
                "status": Announcement.Status.ACTIVE,
                "description": "Servicio urgente",
                "free_text": "Atendemos festivos",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Organization must be approved for this action.")

    def test_announcement_create_requires_description_and_free_text(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "category": str(self.category.uuid),
                "name": "Invalid Announcement",
                "location": "Madrid",
                "title": "No valida",
                "status": Announcement.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("description", response.data)
        self.assertIn("free_text", response.data)

    def test_announcement_list_hides_foreign_organization_from_authenticated_user(self):
        self.client.force_authenticate(user=self.other_owner)

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_organization_announcement_detail_get_is_not_available(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse(
                "organization-announcement-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.view_count, 0)

    def test_public_announcement_detail_increments_announcement_view_count_only_once_per_client(self):
        first_response = self.client.get(
            reverse("public-announcement-detail", kwargs={"uuid": self.announcement.uuid})
        )
        second_response = self.client.get(
            reverse("public-announcement-detail", kwargs={"uuid": self.announcement.uuid})
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.view_count, 1)
        self.assertNotIn("review", first_response.data)

    def test_announcement_review_is_one_to_one(self):
        with self.assertRaises(IntegrityError):
            AnnouncementReview.objects.create(
                announcement=self.announcement,
                content="Duplicated review",
            )

    def test_organization_write_is_throttled(self):
        cache.clear()
        self.client.force_authenticate(user=self.owner)

        class OrganizationWriteTestThrottle(SimpleRateThrottle):
            scope = "organization_write_test"
            rate = "1/minute"

            def get_cache_key(self, request, view):
                return self.cache_format % {
                    "scope": self.scope,
                    "ident": self.get_ident(request),
                }

        with patch.object(OrganizationViewSet, "throttle_classes", [OrganizationWriteTestThrottle]):
            first_response = self.client.patch(
                reverse("organization-me"),
                {"name": "Acme Updated Once"},
                format="json",
            )
            second_response = self.client.patch(
                reverse("organization-me"),
                {"name": "Acme Updated Twice"},
                format="json",
            )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class OrganizationPricingModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pricing-owner",
            email="pricing-owner@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.user,
            name="Pricing Org",
            legal_name="Pricing Org SL",
            tax_id="P123",
            billing_email="billing@pricing.example.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            is_approved=True,
        )
        self.default_plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="test-pricing-default",
            defaults={
                "name": "Test Pricing Default",
                "description": "Tier base",
                "sort_order": 10,
            },
        )
        self.pro_plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="test-pricing-pro",
            defaults={
                "name": "Test Pricing Pro",
                "description": "Tier pro",
                "sort_order": 20,
            },
        )

    def test_organization_pricing_persists_plan_and_flags(self):
        pricing = OrganizationPricing.objects.create(
            organization=self.organization,
            plan_tier=self.pro_plan_tier,
            monthly_price="49.99",
            commission_rate="12.50",
            feature_flags={"priority_support": True, "custom_branding": False},
        )

        self.assertEqual(pricing.organization, self.organization)
        self.assertEqual(pricing.plan_tier, self.pro_plan_tier)
        self.assertEqual(str(pricing.monthly_price), "49.99")
        self.assertEqual(str(pricing.commission_rate), "12.50")
        self.assertEqual(
            pricing.feature_flags,
            {"priority_support": True, "custom_branding": False},
        )

    def test_organization_can_only_have_one_pricing_row(self):
        OrganizationPricing.objects.create(
            organization=self.organization,
            plan_tier=self.default_plan_tier,
            monthly_price="19.99",
            commission_rate="10.00",
        )

        with self.assertRaises(IntegrityError):
            OrganizationPricing.objects.create(
                organization=self.organization,
                plan_tier=self.pro_plan_tier,
                monthly_price="79.99",
                commission_rate="8.50",
            )

    def test_organization_pricing_rejects_commission_rate_above_100_percent(self):
        pricing = OrganizationPricing(
            organization=self.organization,
            plan_tier=self.pro_plan_tier,
            monthly_price="49.99",
            commission_rate="120.00",
        )

        with self.assertRaises(ValidationError):
            pricing.full_clean()


class AnnouncementSerializerTests(SimpleTestCase):
    def test_serializer_does_not_expose_announcement_review_field(self):
        from .serializers import AnnouncementSerializer

        serializer = AnnouncementSerializer()

        self.assertNotIn("review", serializer.get_fields())

    def test_announcement_serializer_uses_title_and_requires_text_fields(self):
        from .serializers import AnnouncementSerializer

        serializer = AnnouncementSerializer()

        self.assertIn("title", serializer.get_fields())
        self.assertNotIn("announcement", serializer.get_fields())
        self.assertTrue(serializer.get_fields()["title"].required)
        self.assertTrue(serializer.get_fields()["description"].required)
        self.assertTrue(serializer.get_fields()["free_text"].required)

    @override_settings(MEDIA_URL="/s3/bravo-media/")
    def test_announcement_image_serializer_normalizes_absolute_storage_url_to_public_s3_path(self):
        from .serializers import AnnouncementImageSerializer

        announcement_uuid = uuid.uuid4()
        image = type(
            "ImageStub",
            (),
            {
                "uuid": uuid.uuid4(),
                "announcement": type("AnnouncementStub", (), {"uuid": announcement_uuid})(),
                "image": type(
                    "FileStub",
                    (),
                    {
                        "name": "announcements/test.png",
                        "url": "https://files.example.com/bravo-media/announcements/test.png?signature=abc",
                    },
                )(),
                "created_at": None,
            },
        )()
        request = RequestFactory().get("/api/announcements/")
        serializer = AnnouncementImageSerializer(instance=image, context={"request": request})

        self.assertEqual(
            serializer.data["image_url"],
            "http://testserver/s3/bravo-media/announcements/test.png?signature=abc",
        )
        self.assertEqual(
            serializer.data["base64_url"],
            f"http://testserver/api/announcements/{announcement_uuid}/images/{image.uuid}/base64/",
        )
        self.assertEqual(serializer.data["filename"], "test.png")

    def test_service_price_serializer_accepts_subservice_for_write(self):
        from .serializers import ServicePriceSerializer

        serializer = ServicePriceSerializer()

        self.assertIn("subservice", serializer.get_fields())
        self.assertFalse(serializer.get_fields()["subservice"].read_only)

    def test_service_serializer_exposes_subservices_as_read_only(self):
        from .serializers import ServiceSerializer

        serializer = ServiceSerializer()

        self.assertTrue(serializer.get_fields()["subservices"].read_only)


class AnnouncementViewCountMiddlewareTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="middleware-owner",
            email="middleware-owner@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.owner,
            name="Middleware Org",
            legal_name="Middleware Org SL",
            tax_id="M123",
            billing_email="billing@middleware.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            is_approved=True,
        )
        self.category = Category.objects.create(name="Middleware Category")
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Middleware Announcement",
            location="Madrid",
            announcement="Middleware Promo",
            status=Announcement.Status.ACTIVE,
            description="Middleware description",
            free_text="Middleware text",
        )
        self.factory = RequestFactory()
        cache.clear()

    def test_anonymous_visitor_is_counted_only_once_per_session(self):
        request = self._build_anonymous_request()
        duplicate_request = self._build_anonymous_request(session_key="anon-visitor")
        middleware = AnnouncementViewCountMiddleware(lambda incoming_request: None)

        middleware._track_announcement_view(request)
        middleware._track_announcement_view(duplicate_request)

        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.view_count, 1)

    def _build_anonymous_request(self, session_key="anon-visitor"):
        request = self.factory.get(
            reverse(
                "public-announcement-detail",
                kwargs={"uuid": self.announcement.uuid},
            )
        )
        session_middleware = SessionMiddleware(lambda incoming_request: None)
        session_middleware.process_request(request)
        request.session.save()
        request.session._session_key = session_key
        request.user = AnonymousUser()
        request.resolver_match = self._resolver_match()
        return request

    def _resolver_match(self):
        class ResolverMatch:
            url_name = "public-announcement-detail"
            kwargs = {"uuid": self.announcement.uuid}

        return ResolverMatch()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    MEDIA_ROOT="/tmp/bravo-organization-tests-media",
    MEDIA_URL="/s3/test-bucket/",
    ORGANIZATION_ANNOUNCEMENT_IMAGE_ALLOWED_CONTENT_TYPES=("image/png", "image/jpeg"),
    ORGANIZATION_ANNOUNCEMENT_IMAGE_MAX_BYTES=1024,
)
class AnnouncementImageApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="announcement-image-owner",
            email="announcement-image-owner@example.com",
            password="testpass123",
        )
        self.other_user = user_model.objects.create_user(
            username="announcement-image-other",
            email="announcement-image-other@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.owner,
            name="Image Org",
            legal_name="Image Org SL",
            tax_id="IMG123",
            billing_email="billing@image-org.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            is_approved=True,
        )
        self.category = Category.objects.create(name="Image Category")
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Image Announcement",
            location="Madrid",
            announcement="Con imagen",
            status=Announcement.Status.ACTIVE,
            description="Descripcion",
            free_text="Texto libre",
        )

    def _make_png_upload(self, name="announcement.png"):
        image_io = io.BytesIO()
        Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_io, format="PNG")
        image_io.seek(0)
        return SimpleUploadedFile(name, image_io.getvalue(), content_type="image/png")

    def _make_png_bytes(self):
        image_io = io.BytesIO()
        Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_io, format="PNG")
        return image_io.getvalue()

    def test_owner_cannot_request_direct_upload_with_filesystem_storage(self):
        self.client.force_authenticate(user=self.owner)
        image_bytes = self._make_png_bytes()

        response = self.client.post(
            reverse(
                "organization-announcement-image-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            ),
            {
                "filename": "announcement.png",
                "content_type": "image/png",
                "size_bytes": len(image_bytes),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AnnouncementImage.objects.count(), 0)
        self.assertEqual(response.data[0], "Direct upload is not supported by the configured storage.")

    def test_non_owner_cannot_upload_announcement_image(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            reverse(
                "organization-announcement-image-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            ),
            {"image": self._make_png_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(AnnouncementImage.objects.count(), 0)

    def test_announcement_detail_includes_uploaded_images(self):
        AnnouncementImage.objects.create(
            announcement=self.announcement,
            image=self._make_png_upload(name="detail.png"),
        )

        response = self.client.get(
            reverse("public-announcement-detail", kwargs={"uuid": self.announcement.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["images"]), 1)
        self.assertIn(
            "/s3/test-bucket/organization-announcements/",
            response.data["images"][0]["image_url"],
        )
        self.assertIn(
            f"/api/announcements/{self.announcement.uuid}/images/",
            response.data["images"][0]["base64_url"],
        )
        self.assertTrue(response.data["images"][0]["base64_url"].endswith("/base64/"))
        self.assertTrue(response.data["images"][0]["filename"].startswith("detail"))
        self.assertTrue(response.data["images"][0]["filename"].endswith(".png"))

    def test_owner_can_get_announcement_image_as_base64(self):
        image_bytes = self._make_png_bytes()
        image = AnnouncementImage.objects.create(
            announcement=self.announcement,
            image=SimpleUploadedFile("inline.png", image_bytes, content_type="image/png"),
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse(
                "organization-announcement-image-base64",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                    "image_uuid": image.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(image.uuid))
        self.assertTrue(response.data["filename"].startswith("inline"))
        self.assertTrue(response.data["filename"].endswith(".png"))
        self.assertEqual(response.data["content_type"], "image/png")
        self.assertEqual(
            response.data["data"],
            base64.b64encode(image_bytes).decode("ascii"),
        )

    def test_non_owner_cannot_get_announcement_image_as_base64(self):
        image = AnnouncementImage.objects.create(
            announcement=self.announcement,
            image=self._make_png_upload(name="inline.png"),
        )
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(
            reverse(
                "organization-announcement-image-base64",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                    "image_uuid": image.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_can_get_active_announcement_image_as_base64(self):
        image_bytes = self._make_png_bytes()
        image = AnnouncementImage.objects.create(
            announcement=self.announcement,
            image=SimpleUploadedFile("public-inline.png", image_bytes, content_type="image/png"),
        )

        response = self.client.get(
            reverse(
                "public-announcement-image-base64",
                kwargs={"uuid": self.announcement.uuid, "image_uuid": image.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(image.uuid))
        self.assertTrue(response.data["filename"].startswith("public-inline"))
        self.assertTrue(response.data["filename"].endswith(".png"))
        self.assertEqual(response.data["content_type"], "image/png")
        self.assertEqual(
            response.data["data"],
            base64.b64encode(image_bytes).decode("ascii"),
        )

    def test_public_base64_returns_404_for_inactive_announcement(self):
        self.announcement.status = Announcement.Status.CLOSED
        self.announcement.save(update_fields=["status"])
        image = AnnouncementImage.objects.create(
            announcement=self.announcement,
            image=self._make_png_upload(name="closed.png"),
        )

        response = self.client.get(
            reverse(
                "public-announcement-image-base64",
                kwargs={"uuid": self.announcement.uuid, "image_uuid": image.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_rejects_invalid_content_type(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-announcement-image-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            ),
            {
                "filename": "announcement.txt",
                "content_type": "text/plain",
                "size_bytes": len(b"plain text"),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content_type", response.data)

    def test_owner_can_delete_announcement_image(self):
        image = AnnouncementImage.objects.create(
            announcement=self.announcement,
            image=self._make_png_upload(name="delete.png"),
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.delete(
            reverse(
                "organization-announcement-image-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                    "image_uuid": image.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AnnouncementImage.objects.filter(pk=image.pk).exists())
