import asyncio
from datetime import date
from unittest import skipUnless
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.testing import WebsocketCommunicator
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.db import connections, transaction
from django.db.utils import IntegrityError
from django.test import RequestFactory, SimpleTestCase, TransactionTestCase, override_settings
from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .middleware import AnnouncementViewCountMiddleware
from .models import (
    Announcement,
    AnnouncementReview,
    Category,
    Organization,
    OrganizationJob,
    Service,
    ServicePrice,
    Subservice,
)
from .routing import websocket_urlpatterns
from .views import OrganizationViewSet

JOBS_INSTALLED = django_apps.is_installed("apps.jobs")

if JOBS_INSTALLED:
    from apps.job_chat.ws_auth import JWTAuthMiddlewareStack
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
        self.owner_organization_job = OrganizationJob.objects.create(
            organization=self.organization,
            name="Cleaning",
            description="Cleaning services",
        )
        self.other_organization_job = OrganizationJob.objects.create(
            organization=self.other_organization,
            name="Pet Care",
            description="Pet services",
        )
        self.owner_service = Service.objects.create(
            job=self.owner_organization_job,
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
            job=self.other_organization_job,
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

    def test_organization_root_get_is_not_available_as_list(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("organization-list"))

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

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

    def test_organization_jobs_list_is_public(self):
        response = self.client.get(
            reverse("organization-job-list", kwargs={"organization_uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.owner_organization_job.uuid))

    def test_public_job_list_hides_unapproved_organization(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])

        response = self.client.get(
            reverse("organization-job-list", kwargs={"organization_uuid": self.organization.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_organization_job_crud_for_owner(self):
        self.client.force_authenticate(user=self.owner)

        create_response = self.client.post(
            reverse("organization-job-list", kwargs={"organization_uuid": self.organization.uuid}),
            {"name": "Repairs", "description": "Repair services"},
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_job_uuid = create_response.data["uuid"]
        self.assertEqual(create_response.data["organization"], str(self.organization.uuid))

        update_response = self.client.patch(
            reverse(
                "organization-job-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": created_job_uuid,
                },
            ),
            {"name": "Repairs Updated"},
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "Repairs Updated")

        delete_response = self.client.delete(
            reverse(
                "organization-job-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": created_job_uuid,
                },
            )
        )

        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(OrganizationJob.objects.filter(uuid=created_job_uuid).exists())

    def test_unapproved_organization_cannot_create_job(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse("organization-job-list", kwargs={"organization_uuid": self.organization.uuid}),
            {"name": "Repairs", "description": "Repair services"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Organization must be approved for this action.")

    def test_services_list_is_public(self):
        response = self.client.get(
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_services_list_is_public_and_returns_services_for_requested_organization(self):
        response = self.client.get(
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertEqual(returned_uuids, {str(self.owner_service.uuid)})

    def test_services_list_is_paginated(self):
        Service.objects.create(
            job=self.owner_organization_job,
            category=self.category,
            name="Second Owner Plan",
            description="Second service",
        )

        response = self.client.get(
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                },
            ),
            {"page_size": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])

    def test_service_retrieve_is_public_by_uuid(self):
        response = self.client.get(
            reverse(
                "organization-service-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.owner_service.uuid))
        self.assertEqual(response.data["job"], str(self.owner_organization_job.uuid))
        self.assertEqual(response.data["category"], str(self.category.uuid))
        self.assertNotIn("id", response.data)

    def test_public_service_retrieve_hides_unapproved_organization(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])

        response = self.client.get(
            reverse(
                "organization-service-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_service_crud_for_organization_owner(self):
        self.client.force_authenticate(user=self.owner)

        create_response = self.client.post(
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                },
            ),
            {
                "category": str(self.category.uuid),
                "name": "New Service",
                "description": "Created via API",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_service_uuid = create_response.data["uuid"]
        self.assertEqual(create_response.data["organization"], str(self.organization.uuid))
        self.assertEqual(create_response.data["job"], str(self.owner_organization_job.uuid))
        self.assertEqual(create_response.data["category"], str(self.category.uuid))
        self.assertNotIn("id", create_response.data)

        update_response = self.client.patch(
            reverse(
                "organization-service-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": created_service_uuid,
                },
            ),
            {"name": "Renamed Service"},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "Renamed Service")

        delete_response = self.client.delete(
            reverse(
                "organization-service-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": created_service_uuid,
                },
            )
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Service.objects.filter(uuid=created_service_uuid).exists())

    def test_unapproved_organization_cannot_create_service(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                },
            ),
            {
                "category": str(self.category.uuid),
                "name": "Blocked Service",
                "description": "Created via API",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Organization must be approved for this action.")

    @override_settings(BYPASS_ORGANIZATION_VALIDATION=True)
    def test_bypass_organization_validation_allows_service_creation_for_unapproved_organization(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                },
            ),
            {
                "category": str(self.category.uuid),
                "name": "Bypassed Service",
                "description": "Created via bypass",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["organization"])

    def test_non_owner_cannot_update_service(self):
        self.client.force_authenticate(user=self.other_owner)
        response = self.client.patch(
            reverse(
                "organization-service-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            ),
            {"name": "Hijacked"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.owner_service.refresh_from_db()
        self.assertEqual(self.owner_service.name, "Owner Plan")

    def test_non_owner_cannot_delete_service(self):
        self.client.force_authenticate(user=self.other_owner)
        response = self.client.delete(
            reverse(
                "organization-service-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Service.objects.filter(uuid=self.owner_service.uuid).exists())

    def test_create_service_fails_when_organization_in_url_is_not_owned_by_user(self):
        self.client.force_authenticate(user=self.user_without_organization)
        response = self.client.post(
            reverse(
                "organization-service-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                },
            ),
            {"category": str(self.category.uuid), "name": "Invalid Service", "description": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Organization does not belong to the authenticated user.")

    def test_create_subservice_fails_for_foreign_service(self):
        self.client.force_authenticate(user=self.owner)
        initial_count = Subservice.objects.count()
        response = self.client.post(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "organization_uuid": self.other_organization.uuid,
                    "job_uuid": self.other_organization_job.uuid,
                    "service_uuid": self.other_service.uuid,
                },
            ),
            {
                "service": str(self.other_service.uuid),
                "name": "Illegal subservice",
                "description": "Should fail by ownership",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Subservice.objects.count(), initial_count)

    def test_unapproved_organization_cannot_create_subservice(self):
        self.organization.is_approved = False
        self.organization.save(update_fields=["is_approved"])
        self.client.force_authenticate(user=self.owner)
        initial_count = Subservice.objects.count()

        response = self.client.post(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            ),
            {
                "service": str(self.owner_service.uuid),
                "name": "Blocked subservice",
                "description": "Should fail by approval",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Organization must be approved for this action.")
        self.assertEqual(Subservice.objects.count(), initial_count)

    def test_subservice_list_filters_by_service_uuid_in_path(self):
        self.client.force_authenticate(user=self.owner)
        second_service = Service.objects.create(
            job=self.owner_organization_job,
            category=self.category,
            name="Second Service",
            description="Another owner service",
        )
        matching = Subservice.objects.create(
            service=self.owner_service,
            name="Matching",
            description="Visible subservice",
        )
        Subservice.objects.create(
            service=second_service,
            name="Non Matching",
            description="Should be excluded",
        )

        response = self.client.get(
            reverse(
                "organization-subservice-list",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": self.owner_service.uuid,
                },
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        returned_items = {item["uuid"]: item for item in response.data["results"]}
        self.assertEqual(set(returned_items), {str(self.owner_subservice.uuid), str(matching.uuid)})
        self.assertEqual(str(returned_items[str(matching.uuid)]["service"]), str(self.owner_service.uuid))
        self.assertEqual(
            returned_items[str(self.owner_subservice.uuid)]["service_prices"],
            [
                {
                    "uuid": str(self.owner_service_price.uuid),
                    "amount": "49.99",
                    "currency": "EUR",
                    "charging_type": ServicePrice.ChargingType.PER_PROJECT,
                    "effective_from": "2026-01-01",
                    "effective_to": None,
                    "created_at": self.owner_service_price.created_at.isoformat().replace("+00:00", "Z"),
                    "updated_at": self.owner_service_price.updated_at.isoformat().replace("+00:00", "Z"),
                }
            ],
        )

    def test_subservice_retrieve_uses_nested_organization_and_service_uuids(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse(
                "organization-subservice-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.owner_organization_job.uuid,
                    "service_uuid": self.owner_service.uuid,
                    "uuid": self.owner_subservice.uuid,
                },
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.owner_subservice.uuid))
        self.assertEqual(
            response.data["service_prices"],
            [
                {
                    "uuid": str(self.owner_service_price.uuid),
                    "amount": "49.99",
                    "currency": "EUR",
                    "charging_type": ServicePrice.ChargingType.PER_PROJECT,
                    "effective_from": "2026-01-01",
                    "effective_to": None,
                    "created_at": self.owner_service_price.created_at.isoformat().replace("+00:00", "Z"),
                    "updated_at": self.owner_service_price.updated_at.isoformat().replace("+00:00", "Z"),
                }
            ],
        )

    def test_subservice_nested_path_rejects_mismatched_organization_and_service(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse(
                "organization-subservice-detail",
                kwargs={
                    "organization_uuid": self.organization.uuid,
                    "job_uuid": self.other_organization_job.uuid,
                    "service_uuid": self.other_service.uuid,
                    "uuid": self.other_subservice.uuid,
                },
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_service_price_endpoints_do_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("organization-service-price-list")

        with self.assertRaises(NoReverseMatch):
            reverse("organization-service-price-detail", kwargs={"uuid": self.owner_service_price.uuid})

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
        self.assertEqual(response.data["services"], [str(self.owner_service.uuid)])
        self.assertEqual(response.data["view_count"], 0)
        self.assertNotIn("review", response.data)

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


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
)
class OrganizationSearchWebSocketTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="ws-org-owner",
            email="ws-org-owner@example.com",
            password="testpass123",
            email_verified=True,
        )
        self.other_owner = user_model.objects.create_user(
            username="ws-other-owner",
            email="ws-other-owner@example.com",
            password="testpass123",
            email_verified=True,
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
        )
        self.owner_access_token = str(RefreshToken.for_user(self.owner).access_token)
        Organization.objects.create(
            user=self.other_owner,
            name="Beta",
            legal_name="Beta SL",
            tax_id="B456",
            billing_email="billing@beta.com",
            billing_address="Second 2",
            billing_city="Barcelona",
            billing_country="ES",
            billing_postal_code="08001",
        )
        transaction.commit()

    def tearDown(self):
        cache.clear()
        connections.close_all()
        super().tearDown()

    def test_organization_search_websocket_returns_matching_results_for_anonymous_user(self):
        payload = async_to_sync(self._search_via_websocket)("Acme", authenticated=False)

        self.assertEqual(payload["type"], "search.results")
        self.assertEqual(payload["query"], "Acme")
        self.assertEqual(payload["results"], [])

    def test_organization_search_websocket_returns_validation_error_for_empty_query(self):
        payload = async_to_sync(self._search_via_websocket)("   ")

        self.assertEqual(payload["type"], "search.error")
        self.assertEqual(payload["errors"]["q"], "This field is required.")

    def test_organization_search_websocket_rejects_short_queries(self):
        payload = async_to_sync(self._search_via_websocket)("Ac")

        self.assertEqual(payload["type"], "search.error")
        self.assertEqual(payload["errors"]["q"], "Ensure this field has at least 3 characters.")

    def test_organization_search_websocket_allows_anonymous_connections(self):
        connected, close_event = async_to_sync(self._connect_websocket)(authenticated=False)

        self.assertTrue(connected)
        self.assertIsNone(close_event)

    def test_organization_search_websocket_rejects_invalid_origin(self):
        connected, close_code = async_to_sync(self._connect_websocket)(
            authenticated=True,
            origin="http://evil.example.com",
        )

        self.assertFalse(connected)
        self.assertEqual(close_code, 1000)

    def test_organization_search_websocket_rate_limits_requests(self):
        with override_settings(
            ORGANIZATION_SEARCH_WS_RATE_LIMIT=1,
            ORGANIZATION_SEARCH_WS_RATE_WINDOW=60,
        ):
            first_payload, second_payload = async_to_sync(
                self._rate_limited_search_via_websocket
            )(authenticated=False)

        self.assertEqual(first_payload["type"], "search.results")
        self.assertEqual(second_payload["type"], "search.error")
        self.assertEqual(second_payload["errors"]["detail"], "Rate limit exceeded.")

    def _ws_application(self):
        websocket_app = URLRouter(websocket_urlpatterns)
        if JOBS_INSTALLED:
            websocket_app = JWTAuthMiddlewareStack(websocket_app)
        return AllowedHostsOriginValidator(websocket_app)

    async def _connect_websocket(self, authenticated=True, origin="http://localhost"):
        path = "/ws/organization/search/"
        headers = [(b"origin", origin.encode("utf-8"))]
        if authenticated and JOBS_INSTALLED:
            headers.append((b"authorization", f"Bearer {self.owner_access_token}".encode("utf-8")))
        communicator = WebsocketCommunicator(self._ws_application(), path, headers=headers)
        connected, close_code = await communicator.connect()
        try:
            if connected:
                try:
                    return connected, await communicator.receive_output(timeout=0.2)
                except TimeoutError:
                    return connected, None
            return connected, close_code
        finally:
            if connected:
                try:
                    await communicator.disconnect()
                except asyncio.CancelledError:
                    pass
            try:
                await communicator.wait()
            except asyncio.CancelledError:
                pass

    async def _search_via_websocket(self, query, authenticated=True, origin="http://localhost"):
        path = "/ws/organization/search/"
        headers = [(b"origin", origin.encode("utf-8"))]
        if authenticated and JOBS_INSTALLED:
            headers.append((b"authorization", f"Bearer {self.owner_access_token}".encode("utf-8")))
        communicator = WebsocketCommunicator(self._ws_application(), path, headers=headers)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        try:
            await communicator.send_json_to({"q": query})
            return await communicator.receive_json_from()
        finally:
            await communicator.disconnect()
            await communicator.wait()

    async def _rate_limited_search_via_websocket(self, authenticated=True):
        path = "/ws/organization/search/"
        headers = [(b"origin", b"http://localhost")]
        if authenticated and JOBS_INSTALLED:
            headers.append((b"authorization", f"Bearer {self.owner_access_token}".encode("utf-8")))
        communicator = WebsocketCommunicator(self._ws_application(), path, headers=headers)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        try:
            await communicator.send_json_to({"q": "Acme"})
            first_payload = await communicator.receive_json_from()
            await communicator.send_json_to({"q": "Acme"})
            second_payload = await communicator.receive_json_from()
            return first_payload, second_payload
        finally:
            await communicator.disconnect()
            await communicator.wait()


class AnnouncementSerializerTests(SimpleTestCase):
    def test_serializer_does_not_expose_announcement_review_field(self):
        from .serializers import AnnouncementSerializer

        serializer = AnnouncementSerializer()

        self.assertNotIn("review", serializer.get_fields())

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
