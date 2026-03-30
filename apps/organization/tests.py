import uuid
from datetime import date
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.db.utils import IntegrityError
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from .middleware import AnnouncementViewCountMiddleware
from .models import (
    Announcement,
    AnnouncementReview,
    Category,
    Organization,
    Service,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)
from .views import OrganizationViewSet

JOBS_INSTALLED = django_apps.is_installed("apps.jobs")

if JOBS_INSTALLED:
    from apps.jobs.models import Job


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
        self.other_category = Category.objects.create(
            name="Pet Services",
            description="Servicios para mascotas",
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
        self.owner_service = Service.objects.create(
            organization=self.organization,
            service_catalog=self.owner_service_catalog,
            category=self.category,
            name="Owner Plan",
            description="Owner service",
        )
        self.owner_subservice = Subservice.objects.create(
            service=self.owner_service,
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
        self.other_service = Service.objects.create(
            organization=self.other_organization,
            service_catalog=self.other_service_catalog,
            category=self.other_category,
            name="Other Plan",
            description="Other service",
        )
        self.other_subservice = Subservice.objects.create(
            service=self.other_service,
            name="Other Subservice",
            description="Other subservice",
        )
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
        self.announcement.services.add(self.owner_service)
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

    @skipUnless(JOBS_INSTALLED, "jobs app disabled")
    def test_organization_retrieve_includes_verification_level_and_rating_from_completed_jobs(self):
        self.organization.verification_level = 4
        self.organization.save(update_fields=["verification_level"])
        Job.objects.create(
            user=self.owner,
            announcement=self.announcement,
            plan_price=self.owner_service_price,
            status=Job.Status.COMPLETED,
            organization_rating="4.00",
        )
        Job.objects.create(
            user=self.other_owner,
            announcement=self.announcement,
            plan_price=self.owner_service_price,
            status=Job.Status.COMPLETED,
            organization_rating="2.00",
        )
        Job.objects.create(
            user=self.other_owner,
            announcement=self.announcement,
            plan_price=self.owner_service_price,
            status=Job.Status.PENDING,
            organization_rating="5.00",
        )

        response = self.client.get(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["verification_level"], 4)
        self.assertEqual(response.data["rating"], "3.00")

    def test_organization_search_requires_admin(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("organization-search"), {"search": "Acm"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_organization_search_requires_search_query(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("organization-search"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["search"], "This query parameter is required.")

    def test_organization_search_rejects_short_search_query(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("organization-search"), {"search": "Ac"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["search"], "Ensure this query parameter has at least 3 characters.")

    def test_organization_search_is_available_for_admin(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(reverse("organization-search"), {"search": "Acm"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.organization.uuid))

    def test_organization_search_only_allows_get(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(reverse("organization-search"), {"search": "Acm"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_organization_root_get_is_not_available_as_list(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("organization-list"))

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_category_list_is_public_and_read_only(self):
        response = self.client.get(reverse("organization-category-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertGreaterEqual(response.data["count"], 2)
        self.assertTrue({str(self.category.uuid), str(self.other_category.uuid)}.issubset(returned_uuids))

    def test_category_detail_route_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-category-detail", kwargs={"uuid": self.category.uuid})

    def test_category_services_list_is_public(self):
        response = self.client.get(
            reverse("category-service-list", kwargs={"category_uuid": self.category.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.owner_service_catalog.uuid))
        self.assertEqual(response.data["results"][0]["category"], str(self.category.uuid))

    def test_category_services_list_is_paginated(self):
        second_service_catalog = ServiceCatalog.objects.create(
            category=self.category,
            name="Second Category Service",
            description="Second category service",
        )
        Service.objects.create(
            organization=self.organization,
            service_catalog=second_service_catalog,
            category=self.category,
            name="Second Category Service",
            description="Second category service",
        )

        response = self.client.get(
            reverse("category-service-list", kwargs={"category_uuid": self.category.uuid}),
            {"page_size": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])

    def test_category_services_list_returns_catalog_without_duplicates_from_organization_services(self):
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
        Service.objects.create(
            organization=hidden_organization,
            service_catalog=self.owner_service_catalog,
            category=self.category,
            name="Hidden Service",
            description="Should not duplicate catalog",
        )

        response = self.client.get(
            reverse("category-service-list", kwargs={"category_uuid": self.category.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertEqual(returned_uuids, {str(self.owner_service_catalog.uuid)})

    def test_category_services_list_returns_404_for_unknown_category(self):
        response = self.client.get(
            reverse(
                "category-service-list",
                kwargs={"category_uuid": "00000000-0000-0000-0000-000000000000"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_organization_search_lists_organizations_for_admin(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("organization-search"), {"search": "example.com"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {item["uuid"] for item in response.data["results"]},
            {str(self.organization.uuid), str(self.other_organization.uuid)},
        )

    def test_organization_admin_endpoint_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-admin-list")

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

    def test_owner_can_update_organization_by_uuid(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid}),
            {"name": "Acme Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Acme Updated")

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

    def test_suspended_owner_cannot_update_organization_by_uuid(self):
        self.owner.status = self.owner.Status.SUSPENDED
        self.owner.save(update_fields=["status"])
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid}),
            {"name": "Blocked Update"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Acme")

    def test_non_owner_cannot_update_organization_by_uuid(self):
        self.client.force_authenticate(user=self.other_owner)
        response = self.client.patch(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid}),
            {"name": "Invalid Update"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Acme")

    def test_non_owner_cannot_delete_organization_by_uuid(self):
        self.client.force_authenticate(user=self.other_owner)
        response = self.client.delete(
            reverse("organization-detail", kwargs={"uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Organization.objects.filter(uuid=self.organization.uuid).exists())

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

        with self.assertRaises(NoReverseMatch):
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job_uuid,
                },
            )

        with self.assertRaises(NoReverseMatch):
            reverse(
                "organization-service-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job_uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            )

        with self.assertRaises(NoReverseMatch):
            reverse(
                "organization-subservice-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job_uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            )

        with self.assertRaises(NoReverseMatch):
            reverse(
                "organization-subservice-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job_uuid,
                    "service_uuid": self.owner_service.uuid,
                    "uuid": self.owner_subservice.uuid,
                },
            )

        with self.assertRaises(NoReverseMatch):
            reverse(
                "organization-service-price-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job_uuid,
                    "service_uuid": self.owner_service.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            )

        with self.assertRaises(NoReverseMatch):
            reverse(
                "organization-service-price-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job_uuid,
                    "service_uuid": self.owner_service.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                    "price_uuid": self.owner_service_price.uuid,
                },
            )

    def test_public_nested_subservice_and_price_endpoints_exist(self):
        self.assertEqual(
            reverse(
                "public-subservice-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            ),
            f"/api/organizations/{self.organization.uuid}/services/{self.owner_service.uuid}/subservices/",
        )
        self.assertEqual(
            reverse(
                "public-service-price-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            ),
            (
                f"/api/organizations/{self.organization.uuid}/services/{self.owner_service.uuid}"
                f"/subservices/{self.owner_subservice.uuid}/prices/"
            ),
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
        matching.services.add(self.other_service)
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
        non_matching.services.add(self.owner_service)

        response = self.client.get(
            reverse("public-announcement-list"),
            {"service": str(self.other_service.uuid)},
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
                "announcement": "fontaneria",
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

    def test_public_announcement_detail_is_available_by_organization_and_uuid(self):
        response = self.client.get(
            reverse(
                "public-announcement-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.announcement.uuid))
        self.assertEqual(response.data["organization"], str(self.organization.uuid))
        self.assertEqual(response.data["lowest_price"], "49.99")
        self.assertEqual(response.data["services"][0]["uuid"], str(self.owner_service.uuid))
        self.assertEqual(
            response.data["services"][0]["subservices"][0]["uuid"],
            str(self.owner_subservice.uuid),
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
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_subservice_list_is_available_by_organization_and_service(self):
        response = self.client.get(
            reverse(
                "public-subservice-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.owner_subservice.uuid))

    def test_public_subservice_retrieve_is_available_by_nested_uuids(self):
        response = self.client.get(
            reverse(
                "public-subservice-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
                    "subservice_uuid": self.owner_subservice.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.owner_subservice.uuid))
        self.assertEqual(str(response.data["service"]), str(self.owner_service.uuid))

    def test_public_service_price_list_is_available_by_nested_uuids(self):
        response = self.client.get(
            reverse(
                "public-service-price-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
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
                "public-service-price-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
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
                "public-subservice-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            )
        )
        price_response = self.client.get(
            reverse(
                "public-service-price-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "service_uuid": self.owner_service.uuid,
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
        second_announcement.services.add(self.other_service)

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {"service": str(self.owner_service.uuid)},
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
                "announcement": "jardineria",
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
                "services": [str(self.owner_service.uuid)],
                "name": "Emergency Plumbing",
                "location": "Madrid Centro",
                "announcement": "Atencion 24 horas",
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
        self.assertEqual(response.data["category"], str(self.category.uuid))
        self.assertEqual(response.data["lowest_price"], "49.99")
        self.assertEqual(len(response.data["services"]), 1)
        self.assertEqual(response.data["services"][0]["uuid"], str(self.owner_service.uuid))
        self.assertEqual(len(response.data["services"][0]["subservices"]), 1)
        self.assertEqual(
            response.data["services"][0]["subservices"][0]["uuid"],
            str(self.owner_subservice.uuid),
        )
        self.assertEqual(
            response.data["services"][0]["subservices"][0]["service_prices"][0]["uuid"],
            str(self.owner_service_price.uuid),
        )
        self.assertEqual(response.data["view_count"], 0)
        self.assertNotIn("review", response.data)

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
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": announcement_without_prices.uuid,
                },
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
                "services": [str(self.owner_service.uuid)],
                "name": "Emergency Plumbing",
                "location": "Madrid Centro",
                "announcement": "Atencion 24 horas",
                "status": Announcement.Status.ACTIVE,
                "description": "Servicio urgente",
                "free_text": "Atendemos festivos",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Organization must be approved for this action.")

    def test_announcement_create_rejects_services_from_another_organization(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            ),
            {
                "category": str(self.category.uuid),
                "services": [str(self.other_service.uuid)],
                "name": "Invalid Announcement",
                "location": "Madrid",
                "announcement": "No valida",
                "status": Announcement.Status.ACTIVE,
                "description": "Should fail",
                "free_text": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["services"][0],
            "Services must belong to the organization in the URL.",
        )

    def test_announcement_list_hides_foreign_organization_from_authenticated_user(self):
        self.client.force_authenticate(user=self.other_owner)

        response = self.client.get(
            reverse(
                "organization-announcement-list",
                kwargs={"organization_uuid": self.organization.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_owner_cannot_retrieve_private_announcement(self):
        self.client.force_authenticate(user=self.other_owner)

        response = self.client.get(
            reverse(
                "organization-announcement-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.view_count, 0)

    def test_owner_retrieve_increments_announcement_view_count_only_once_per_client(self):
        self.client.force_authenticate(user=self.owner)

        first_response = self.client.get(
            reverse(
                "organization-announcement-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            )
        )
        second_response = self.client.get(
            reverse(
                "organization-announcement-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
            )
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
                reverse("organization-detail", kwargs={"uuid": self.organization.uuid}),
                {"name": "Acme Updated Once"},
                format="json",
            )
            second_response = self.client.patch(
                reverse("organization-detail", kwargs={"uuid": self.organization.uuid}),
                {"name": "Acme Updated Twice"},
                format="json",
            )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)




class AnnouncementSerializerTests(SimpleTestCase):
    def test_serializer_does_not_expose_announcement_review_field(self):
        from .serializers import AnnouncementSerializer

        serializer = AnnouncementSerializer()

        self.assertNotIn("review", serializer.get_fields())

    def test_serializer_returns_hardcoded_images_list(self):
        from .serializers import AnnouncementSerializer

        serializer = AnnouncementSerializer()

        self.assertEqual(
            serializer.get_images(obj=None),
            [AnnouncementSerializer.HARDCODED_IMAGE_URL] * AnnouncementSerializer.HARDCODED_IMAGE_COUNT,
        )

    def test_service_price_serializer_accepts_subservice_for_write(self):
        from .serializers import ServicePriceSerializer

        serializer = ServicePriceSerializer()

        self.assertIn("subservice", serializer.get_fields())
        self.assertFalse(serializer.get_fields()["subservice"].read_only)


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
                "organization-announcement-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "uuid": self.announcement.uuid,
                },
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
            url_name = "organization-announcement-detail"
            kwargs = {"uuid": self.announcement.uuid}

        return ResolverMatch()
