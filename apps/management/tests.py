import os
import re
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework import status
from rest_framework.test import APITestCase

from apps.job_chat.models import JobChat, JobChatMessage
from apps.jobs.models import Job
from apps.management.feature_flags import is_feature_enabled
from apps.management.models import FeatureFlag
from apps.organization.models import (
    AllowedCity,
    Announcement,
    AnnouncementStatusChange,
    Category,
    Organization,
    OrganizationPricing,
    PlanTierCatalog,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)


class AdminLegalDocumentsBrowserTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="legal-docs-admin",
            email="legal-docs-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="legal-docs-user",
            email="legal-docs-user@example.com",
            password="testpass123",
        )

    def test_admin_index_includes_legal_documents_link(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, reverse("admin:legal-documents-browser"))
        self.assertContains(response, "Documentos legales")

    def test_staff_user_can_browse_nested_legal_documents_and_read_text_file(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            contracts_dir = root / "contracts"
            contracts_dir.mkdir()
            (contracts_dir / "privacy-policy.md").write_text(
                "# Privacy policy\n\nDocumento legal visible desde admin.\n",
                encoding="utf-8",
            )

            with override_settings(LEGAL_DOCUMENTS_ROOT=root):
                self.client.force_login(self.admin_user)

                folder_response = self.client.get(
                    reverse("admin:legal-documents-browser"),
                    {"path": "contracts"},
                )
                file_response = self.client.get(
                    reverse("admin:legal-documents-browser"),
                    {"path": "contracts/privacy-policy.md"},
                )

        self.assertEqual(folder_response.status_code, status.HTTP_200_OK)
        self.assertContains(folder_response, "privacy-policy.md")
        self.assertContains(folder_response, "contracts")
        self.assertEqual(file_response.status_code, status.HTTP_200_OK)
        self.assertContains(file_response, "Documento legal visible desde admin.")

    def test_non_staff_user_cannot_access_legal_documents_browser(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("admin:legal-documents-browser"))

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)


class ManagementApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="platform-admin",
            email="platform-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.staff_candidate = user_model.objects.create_user(
            username="staff-candidate",
            email="staff-candidate@example.com",
            password="testpass123",
        )
        self.organization_owner = user_model.objects.create_user(
            username="managed-owner",
            email="managed-owner@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.organization_owner,
            name="Managed Org",
            legal_name="Managed Org SL",
            tax_id="ORG123",
            billing_email="billing@managed-org.example.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
        )
        self.pro_plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="mgmt-pro",
            defaults={
                "name": "Mgmt Pro",
                "description": "Tier pro",
                "sort_order": 30,
            },
        )
        self.organization_pricing = OrganizationPricing.objects.create(
            organization=self.organization,
            plan_tier=self.pro_plan_tier,
            monthly_price="49.99",
            commission_rate="12.50",
        )

    def test_non_staff_cannot_access_management_endpoints(self):
        self.client.force_authenticate(user=self.staff_candidate)

        response = self.client.get(reverse("management-users-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_list_users_includes_provider_metadata(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        managed_owner = next(
            user for user in response.data["results"] if user["uuid"] == str(self.organization_owner.uuid)
        )
        self.assertTrue(managed_owner["has_organization"])
        self.assertTrue(managed_owner["is_provider"])
        self.assertEqual(managed_owner["organization"]["uuid"], str(self.organization.uuid))
        self.assertEqual(managed_owner["organization"]["name"], self.organization.name)
        self.assertTrue(
            managed_owner["organization"]["admin_url"].endswith(
                f"/admin/organization/organization/{self.organization.pk}/change/"
            )
        )

    def test_admin_can_create_user(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-users-list"),
            {
                "username": "new-managed-user",
                "email": "new-managed-user@example.com",
                "password": "ChangeMe123!",
                "first_name": "New",
                "last_name": "Managed",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "new-managed-user@example.com")
        self.assertEqual(response.data["status"], "active")
        self.assertNotIn("id", response.data)

    def test_admin_cannot_create_staff_users_from_management_endpoint(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-users-list"),
            {
                "username": "new-admin-user",
                "email": "new-admin-user@example.com",
                "password": "ChangeMe123!",
                "is_staff": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_staff", response.data)
        self.assertFalse(
            get_user_model().objects.filter(
                email="new-admin-user@example.com",
                is_staff=True,
            ).exists()
        )

    def test_admin_cannot_create_user_without_password(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-users-list"),
            {
                "username": "passwordless-user",
                "email": "passwordless-user@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_admin_can_suspend_user(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-users-suspend", kwargs={"uuid": self.staff_candidate.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.staff_candidate.refresh_from_db()
        self.assertEqual(self.staff_candidate.status, self.staff_candidate.Status.SUSPENDED)

    def test_admin_can_patch_managed_user_flags(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.patch(
            reverse("management-users-detail", kwargs={"uuid": self.staff_candidate.uuid}),
            {
                "email_verified": True,
                "status": "suspended",
                "is_active": False,
                "is_staff": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.staff_candidate.refresh_from_db()
        self.assertTrue(self.staff_candidate.email_verified)
        self.assertEqual(self.staff_candidate.status, self.staff_candidate.Status.SUSPENDED)
        self.assertFalse(self.staff_candidate.is_active)
        self.assertTrue(self.staff_candidate.is_staff)

    def test_admin_can_promote_managed_user_to_admin_role(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.patch(
            reverse("management-users-detail", kwargs={"uuid": self.staff_candidate.uuid}),
            {
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.staff_candidate.refresh_from_db()
        self.assertTrue(self.staff_candidate.is_staff)
        self.assertTrue(self.staff_candidate.is_superuser)

    def test_non_staff_cannot_patch_managed_user(self):
        self.client.force_authenticate(user=self.staff_candidate)

        response = self.client.patch(
            reverse("management-users-detail", kwargs={"uuid": self.organization_owner.uuid}),
            {"email_verified": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_deactivate_organization(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse(
                "management-organizations-deactivate",
                kwargs={"uuid": self.organization.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.status, Organization.Status.INACTIVE)

    def test_admin_can_patch_organization(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.patch(
            reverse("management-organizations-detail", kwargs={"uuid": self.organization.uuid}),
            {
                "name": "Managed Org Updated",
                "billing_email": "new-billing@managed-org.example.com",
                "verification_level": 4,
                "status": Organization.Status.SUSPENDED,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Managed Org Updated")
        self.assertEqual(self.organization.billing_email, "new-billing@managed-org.example.com")
        self.assertEqual(self.organization.verification_level, 4)
        self.assertEqual(self.organization.status, Organization.Status.SUSPENDED)

    def test_admin_can_create_organization(self):
        managed_user = get_user_model().objects.create_user(
            username="new-org-owner",
            email="new-org-owner@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-organizations-list"),
            {
                "user": str(managed_user.uuid),
                "name": "Brand New Org",
                "legal_name": "Brand New Org SL",
                "tax_id": "NEW123",
                "billing_email": "billing@brand-new-org.example.com",
                "billing_address": "Fourth 4",
                "billing_city": "Bilbao",
                "billing_country": "ES",
                "billing_postal_code": "48001",
                "verification_level": 2,
                "status": Organization.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Brand New Org")
        self.assertEqual(response.data["verification_level"], 2)
        self.assertIsNone(response.data["plan_tier"])
        self.assertEqual(response.data["status"], Organization.Status.ACTIVE)

    def test_admin_cannot_create_second_organization_for_same_user(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-organizations-list"),
            {
                "user": str(self.organization_owner.uuid),
                "name": "Duplicate Managed Org",
                "legal_name": "Duplicate Managed Org SL",
                "tax_id": "DUP123",
                "billing_email": "billing@duplicate-managed-org.example.com",
                "billing_address": "Fifth 5",
                "billing_city": "Sevilla",
                "billing_country": "ES",
                "billing_postal_code": "41001",
                "status": Organization.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["user"][0], "Selected user already has an organization.")


class ManagementAnnouncementApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="announcement-admin",
            email="announcement-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.owner = user_model.objects.create_user(
            username="announcement-owner",
            email="announcement-owner@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.owner,
            name="Announcements Org",
            legal_name="Announcements Org SL",
            tax_id="ANN123",
            billing_email="billing@announcements-org.example.com",
            billing_address="Gran Via 10",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28013",
        )
        self.category = Category.objects.create(
            name="Announcements Category",
            description="Categoria para management announcements",
        )
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Managed Announcement",
            location="Madrid",
            announcement="Managed announcement",
            description="Managed description",
            free_text="Managed free text",
            status=Announcement.Status.ACTIVE,
        )

    def test_admin_can_list_management_announcements(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-announcements-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.announcement.uuid))
        self.assertEqual(response.data["results"][0]["organization"], str(self.organization.uuid))

    def test_admin_can_filter_management_announcements_by_status(self):
        archived_announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Archived Announcement",
            location="Bilbao",
            announcement="Archived plan",
            status=Announcement.Status.CLOSED,
            description="Archived description",
            free_text="Archived free text",
        )
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("management-announcements-list"),
            {"status": Announcement.Status.CLOSED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(archived_announcement.uuid))

    def test_admin_can_suspend_management_announcement_and_log_status_change(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-announcements-suspend", kwargs={"uuid": self.announcement.uuid}),
            {
                "reason": AnnouncementStatusChange.ChangeReason.ADMIN_DECISION,
                "reason_text": "Suspension aplicada desde management.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Announcement.Status.SUSPENDED)

        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.status, Announcement.Status.SUSPENDED)

        status_change = self.announcement.status_changes.get()
        self.assertEqual(status_change.from_status, Announcement.Status.ACTIVE)
        self.assertEqual(status_change.to_status, Announcement.Status.SUSPENDED)
        self.assertEqual(
            status_change.reason,
            AnnouncementStatusChange.ChangeReason.ADMIN_DECISION,
        )
        self.assertEqual(status_change.reason_text, "Suspension aplicada desde management.")
        self.assertEqual(status_change.changed_by, "admin")

    def test_suspended_admin_cannot_access_management_endpoints(self):
        self.admin_user.status = self.admin_user.Status.SUSPENDED
        self.admin_user.save(update_fields=["status"])
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ManagementOrganizationListApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-list-admin",
            email="management-list-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.organization_owner = user_model.objects.create_user(
            username="management-list-owner",
            email="management-list-owner@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.organization_owner,
            name="Managed List Org",
            legal_name="Managed List Org SL",
            tax_id="LIST123",
            billing_email="billing@managed-list-org.example.com",
            billing_address="Main 10",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28010",
        )
        self.default_plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="mgmt-default",
            defaults={
                "name": "Mgmt Default",
                "description": "Tier base",
                "sort_order": 10,
            },
        )
        OrganizationPricing.objects.create(
            organization=self.organization,
            plan_tier=self.default_plan_tier,
            monthly_price="29.99",
            commission_rate="10.00",
        )

    def test_admin_can_list_organizations_from_management_endpoint(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-organizations-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.organization.uuid))
        self.assertEqual(response.data["results"][0]["plan_tier"]["key"], "mgmt-default")


class ManagementJobApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-jobs-admin",
            email="management-jobs-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="management-jobs-user",
            email="management-jobs-user@example.com",
            password="testpass123",
        )
        self.provider_user = user_model.objects.create_user(
            username="management-jobs-provider",
            email="management-jobs-provider@example.com",
            password="testpass123",
        )
        self.requester = user_model.objects.create_user(
            username="management-jobs-requester",
            email="management-jobs-requester@example.com",
            password="testpass123",
            first_name="Maria",
            last_name="Requester",
        )
        self.category = Category.objects.create(
            name="Management Jobs Category",
            description="Categoria para jobs management",
        )
        self.organization = Organization.objects.create(
            user=self.provider_user,
            name="Management Jobs Org",
            legal_name="Management Jobs Org SL",
            tax_id="MGMTJOB123",
            billing_email="billing@management-jobs-org.example.com",
            billing_address="Main 11",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28011",
        )
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Managed Job Announcement",
            location="Madrid",
            announcement="Managed job announcement",
            description="Managed jobs description",
            free_text="Managed jobs free text",
            status=Announcement.Status.ACTIVE,
        )
        self.service = ServiceCatalog.objects.create(
            category=self.category,
            name="Managed Service",
            description="Servicio para jobs management",
        )
        self.subservice = Subservice.objects.create(
            announcement=self.announcement,
            service_catalog=self.service,
            name="Managed Subservice",
            description="Subservice for jobs management",
        )
        self.price = ServicePrice.objects.create(
            subservice=self.subservice,
            amount="99.00",
            currency="EUR",
            charging_type=ServicePrice.ChargingType.PER_PROJECT,
            effective_from=date(2026, 1, 1),
        )
        self.job = Job.objects.create(
            user=self.requester,
            announcement=self.announcement,
            status=Job.Status.PENDING,
            plan_price=self.price,
            organization_rating="4.50",
        )
        self.chat = JobChat.objects.create(job=self.job)
        self.message = JobChatMessage.objects.create(
            job_chat=self.chat,
            user=self.requester,
            content="Necesito confirmar detalles del presupuesto.",
        )

    def test_admin_can_list_management_jobs(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-jobs-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(result["uuid"], str(self.job.uuid))
        self.assertEqual(result["status"], Job.Status.PENDING)
        self.assertEqual(result["user"]["uuid"], str(self.requester.uuid))
        self.assertEqual(result["provider"]["uuid"], str(self.organization.uuid))
        self.assertEqual(result["announcement"]["uuid"], str(self.announcement.uuid))
        self.assertEqual(result["plan_price"]["uuid"], str(self.price.uuid))
        self.assertEqual(str(result["chat"]["uuid"]), str(self.chat.uuid))

    def test_admin_can_filter_management_jobs_by_status(self):
        Job.objects.create(
            user=self.requester,
            announcement=self.announcement,
            status=Job.Status.SUSPENDED,
        )
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("management-jobs-list"),
            {"status": Job.Status.SUSPENDED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["status"], Job.Status.SUSPENDED)

    def test_admin_can_search_management_jobs(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("management-jobs-list"),
            {"search": "Management Jobs Org"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.job.uuid))

    def test_admin_can_suspend_management_job(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-jobs-suspend", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.SUSPENDED)

    def test_non_staff_cannot_access_management_jobs(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("management-jobs-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ManagementChatApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-chats-admin",
            email="management-chats-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="management-chats-user",
            email="management-chats-user@example.com",
            password="testpass123",
        )
        self.provider_user = user_model.objects.create_user(
            username="management-chats-provider",
            email="management-chats-provider@example.com",
            password="testpass123",
        )
        self.requester = user_model.objects.create_user(
            username="management-chats-requester",
            email="management-chats-requester@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(
            name="Management Chats Category",
            description="Categoria para chats management",
        )
        self.organization = Organization.objects.create(
            user=self.provider_user,
            name="Management Chats Org",
            legal_name="Management Chats Org SL",
            tax_id="MGMTCHAT123",
            billing_email="billing@management-chats-org.example.com",
            billing_address="Second 22",
            billing_city="Valencia",
            billing_country="ES",
            billing_postal_code="46001",
        )
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Managed Chat Announcement",
            location="Valencia",
            announcement="Managed chat announcement",
            description="Managed chats description",
            free_text="Managed chats free text",
            status=Announcement.Status.ACTIVE,
        )
        self.job = Job.objects.create(
            user=self.requester,
            announcement=self.announcement,
            status=Job.Status.ACTIVE,
        )
        self.chat = JobChat.objects.create(job=self.job)
        self.first_message = JobChatMessage.objects.create(
            job_chat=self.chat,
            user=self.requester,
            content="Primer mensaje del hilo.",
        )
        self.second_message = JobChatMessage.objects.create(
            job_chat=self.chat,
            user=self.provider_user,
            content="Respuesta del proveedor en el hilo.",
        )

    def test_admin_can_list_management_chats(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-chats-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(result["uuid"], str(self.chat.uuid))
        self.assertEqual(result["job_uuid"], str(self.job.uuid))
        self.assertEqual(result["message_count"], 2)
        self.assertEqual(result["provider"]["uuid"], str(self.organization.uuid))

    def test_admin_can_search_management_chats_by_message_content(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("management-chats-list"),
            {"search": "proveedor"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.chat.uuid))

    def test_admin_can_retrieve_management_chat_detail(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("management-chats-detail", kwargs={"job_uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["uuid"], str(self.chat.uuid))
        self.assertEqual(response.data["job_uuid"], str(self.job.uuid))
        self.assertEqual(response.data["message_count"], 2)
        self.assertEqual(response.data["messages"]["count"], 2)
        self.assertEqual(len(response.data["messages"]["results"]), 2)
        self.assertEqual(
            response.data["messages"]["results"][0]["uuid"],
            str(self.first_message.uuid),
        )

    def test_non_staff_cannot_access_management_chats(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("management-chats-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ManagementUserListApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-users-admin",
            email="management-users-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="management-users-regular",
            email="management-users-regular@example.com",
            password="testpass123",
        )
        self.alpha_user = user_model.objects.create_user(
            username="mario-admin",
            email="mario@example.com",
            password="testpass123",
            first_name="Mario",
            last_name="Rossi",
            email_verified=True,
            status=user_model.Status.ACTIVE,
        )
        self.beta_user = user_model.objects.create_user(
            username="lucia-ops",
            email="lucia@example.com",
            password="testpass123",
            first_name="Lucia",
            last_name="Lopez",
            email_verified=False,
            status=user_model.Status.ACTIVE,
        )
        self.gamma_user = user_model.objects.create_user(
            username="paused-user",
            email="paused@example.com",
            password="testpass123",
            first_name="Paula",
            last_name="Suspendida",
            email_verified=False,
            status=user_model.Status.SUSPENDED,
        )

    def test_admin_can_search_users_by_username(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"), {"search": "mario"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.alpha_user.uuid))

    def test_admin_can_search_users_by_email(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"), {"search": "lucia@example.com"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.beta_user.uuid))

    def test_admin_can_search_users_by_uuid(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("management-users-list"),
            {"search": str(self.gamma_user.uuid)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.gamma_user.uuid))

    def test_admin_can_filter_users_by_status(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"), {"status": "suspended"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.gamma_user.uuid))

    def test_admin_can_filter_users_by_email_verified_true(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"), {"email_verified": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.alpha_user.uuid))

    def test_admin_can_filter_users_by_email_verified_false(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"), {"email_verified": "false"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertEqual(response.data["count"], 4)
        self.assertSetEqual(
            returned_uuids,
            {
                str(self.regular_user.uuid),
                str(self.beta_user.uuid),
                str(self.gamma_user.uuid),
                str(self.admin_user.uuid),
            },
        )

    def test_admin_can_combine_filters_with_pagination(self):
        self.client.force_authenticate(user=self.admin_user)
        user_model = get_user_model()
        first_match = user_model.objects.create_user(
            username="lucia-extra-1",
            email="lucia-extra-1@example.com",
            password="testpass123",
            first_name="Lucia",
            email_verified=True,
            status=user_model.Status.ACTIVE,
        )
        second_match = user_model.objects.create_user(
            username="lucia-extra-2",
            email="lucia-extra-2@example.com",
            password="testpass123",
            first_name="Lucia",
            email_verified=True,
            status=user_model.Status.ACTIVE,
        )

        response = self.client.get(
            reverse("management-users-list"),
            {
                "search": "lucia",
                "status": user_model.Status.ACTIVE,
                "email_verified": "true",
                "page": 2,
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(second_match.uuid))
        self.assertNotEqual(response.data["results"][0]["uuid"], str(first_match.uuid))

    def test_non_admin_access_remains_rejected_for_filtered_list(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(
            reverse("management-users-list"),
            {"search": "mario", "status": "active", "email_verified": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ManagementFeatureFlagApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="feature-flag-admin",
            email="feature-flag-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="feature-flag-user",
            email="feature-flag-user@example.com",
            password="testpass123",
        )
        self.feature_flag = FeatureFlag.objects.create(
            key="organization_search_v2",
            name="Organization search v2",
            description="Enables the second organization search implementation.",
            is_active=False,
        )

    def test_admin_can_create_feature_flag(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-feature-flags-list"),
            {
                "key": "jobs_bulk_actions",
                "name": "Jobs bulk actions",
                "description": "Enables bulk job management actions.",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["key"], "jobs_bulk_actions")
        self.assertTrue(response.data["is_active"])
        self.assertTrue(FeatureFlag.objects.filter(key="jobs_bulk_actions", is_active=True).exists())

    def test_admin_can_activate_feature_flag(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse(
                "management-feature-flags-activate",
                kwargs={"uuid": self.feature_flag.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.feature_flag.refresh_from_db()
        self.assertTrue(self.feature_flag.is_active)

    def test_admin_can_deactivate_feature_flag(self):
        self.feature_flag.is_active = True
        self.feature_flag.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse(
                "management-feature-flags-deactivate",
                kwargs={"uuid": self.feature_flag.uuid},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.feature_flag.refresh_from_db()
        self.assertFalse(self.feature_flag.is_active)

    def test_non_staff_cannot_manage_feature_flags(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("management-feature-flags-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_feature_flag_key_must_be_unique(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-feature-flags-list"),
            {
                "key": self.feature_flag.key,
                "name": "Duplicate key",
                "description": "",
                "is_active": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("key", response.data)


class ManagementCategoryApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-category-admin",
            email="management-category-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="management-category-user",
            email="management-category-user@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(
            name="Reformas",
            description="Servicios de reforma",
        )

    def test_admin_can_list_categories(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-categories-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertGreaterEqual(response.data["count"], 1)
        self.assertIn(str(self.category.uuid), returned_uuids)

    def test_admin_can_crud_categories(self):
        self.client.force_authenticate(user=self.admin_user)

        create_response = self.client.post(
            reverse("management-categories-list"),
            {"name": "Mantenimiento", "description": "Servicios de mantenimiento"},
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_uuid = create_response.data["uuid"]

        retrieve_response = self.client.get(
            reverse("management-categories-detail", kwargs={"uuid": created_uuid})
        )
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.data["name"], "Mantenimiento")

        update_response = self.client.patch(
            reverse("management-categories-detail", kwargs={"uuid": created_uuid}),
            {"description": "Servicios recurrentes"},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["description"], "Servicios recurrentes")

        delete_response = self.client.delete(
            reverse("management-categories-detail", kwargs={"uuid": created_uuid})
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(uuid=created_uuid).exists())

    def test_non_staff_cannot_manage_categories(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("management-categories-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ManagementAllowedCityApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-allowed-city-admin",
            email="management-allowed-city-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="management-allowed-city-user",
            email="management-allowed-city-user@example.com",
            password="testpass123",
        )
        self.allowed_city = AllowedCity.objects.create(name="Madrid")

    def test_admin_can_list_allowed_cities(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-allowed-cities-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {item["uuid"] for item in response.data["results"]}
        self.assertGreaterEqual(response.data["count"], 1)
        self.assertIn(str(self.allowed_city.uuid), returned_uuids)

    def test_admin_can_create_and_update_allowed_cities(self):
        self.client.force_authenticate(user=self.admin_user)

        create_response = self.client.post(
            reverse("management-allowed-cities-list"),
            {"name": "Barcelona"},
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_uuid = create_response.data["uuid"]

        retrieve_response = self.client.get(
            reverse("management-allowed-cities-detail", kwargs={"uuid": created_uuid})
        )
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.data["name"], "Barcelona")

        update_response = self.client.patch(
            reverse("management-allowed-cities-detail", kwargs={"uuid": created_uuid}),
            {"name": "Valencia"},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "Valencia")

    def test_non_staff_cannot_manage_allowed_cities(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("management-allowed-cities-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ManagementPlanTierApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-plan-tier-admin",
            email="management-plan-tier-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="management-plan-tier-user",
            email="management-plan-tier-user@example.com",
            password="testpass123",
        )
        self.plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="mgmt-plan-tier",
            defaults={
                "name": "Mgmt Plan Tier",
                "description": "Tier base",
                "sort_order": 10,
            },
        )

    def test_admin_can_crud_plan_tiers(self):
        self.client.force_authenticate(user=self.admin_user)

        create_response = self.client.post(
            reverse("management-plan-tiers-list"),
            {
                "key": "vip",
                "name": "Vip",
                "description": "Tier personalizado de prueba",
                "sort_order": 90,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_uuid = create_response.data["uuid"]

        retrieve_response = self.client.get(
            reverse("management-plan-tiers-detail", kwargs={"uuid": created_uuid})
        )
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.data["key"], "vip")

        update_response = self.client.patch(
            reverse("management-plan-tiers-detail", kwargs={"uuid": created_uuid}),
            {"description": "Tier con prioridad maxima"},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["description"], "Tier con prioridad maxima")

        delete_response = self.client.delete(
            reverse("management-plan-tiers-detail", kwargs={"uuid": created_uuid})
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PlanTierCatalog.objects.filter(uuid=created_uuid).exists())

    def test_non_staff_cannot_manage_plan_tiers(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("management-plan-tiers-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ManagementServiceCatalogApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="management-service-admin",
            email="management-service-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="management-service-user",
            email="management-service-user@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(
            name="Category Services",
            description="Servicios de categoria",
        )

    def test_admin_can_create_service_catalog(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-services-list"),
            {
                "name": "Nueva instalacion",
                "description": "Servicio creado desde management",
                "category_uuid": str(self.category.uuid),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Nueva instalacion")
        self.assertEqual(response.data["description"], "Servicio creado desde management")
        self.assertEqual(
            response.data["category"],
            {
                "uuid": str(self.category.uuid),
                "name": self.category.name,
            },
        )
        self.assertTrue(
            ServiceCatalog.objects.filter(
                name="Nueva instalacion",
                category=self.category,
            ).exists()
        )

    def test_non_staff_cannot_create_service_catalog(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            reverse("management-services-list"),
            {
                "name": "No autorizado",
                "description": "",
                "category_uuid": str(self.category.uuid),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class FeatureFlagHelperTests(APITestCase):
    def test_returns_default_when_flag_does_not_exist(self):
        self.assertFalse(is_feature_enabled("missing-flag"))
        self.assertTrue(is_feature_enabled("missing-flag", default=True))

    def test_returns_database_state_for_existing_flag(self):
        FeatureFlag.objects.create(
            key="job_chat_uploads",
            name="Job chat uploads",
            is_active=True,
        )

        self.assertTrue(is_feature_enabled("job_chat_uploads"))


class SeedAnnouncementsCommandTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.first_owner = user_model.objects.create_user(
            username="seed-ann-owner-1",
            email="seed-ann-owner-1@example.com",
            password="testpass123",
        )
        self.second_owner = user_model.objects.create_user(
            username="seed-ann-owner-2",
            email="seed-ann-owner-2@example.com",
            password="testpass123",
        )
        self.active_organization_with_services = Organization.objects.create(
            user=self.first_owner,
            name="Seed Org One",
            legal_name="Seed Org One SL",
            tax_id="SEED-ORG-1",
            billing_email="billing1@example.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            status=Organization.Status.ACTIVE,
        )
        self.active_organization_without_services = Organization.objects.create(
            user=self.second_owner,
            name="Seed Org Two",
            legal_name="Seed Org Two SL",
            tax_id="SEED-ORG-2",
            billing_email="billing2@example.com",
            billing_address="Second 2",
            billing_city="Valencia",
            billing_country="ES",
            billing_postal_code="46001",
            status=Organization.Status.ACTIVE,
        )
        self.category = Category.objects.create(
            name="Seed Category",
            description="Categoria para seed announcements",
        )
        self.service_catalog = ServiceCatalog.objects.create(
            category=self.category,
            name="Seed Service",
            description="Seed service",
        )
        self.existing_announcement = Announcement.objects.create(
            organization=self.active_organization_with_services,
            category=self.category,
            name="Seed Service",
            location="Madrid",
            announcement="Seed service available",
        )
        self.subservice = Subservice.objects.create(
            announcement=self.existing_announcement,
            service_catalog=self.service_catalog,
            name="Seed Variant",
            description="Seed service",
        )

    def test_seed_announcements_creates_one_announcement_per_active_organization(self):
        out = StringIO()

        call_command("seed_announcements", stdout=out)

        self.assertEqual(Announcement.objects.count(), 3)
        serviced_announcement = Announcement.objects.get(
            organization=self.active_organization_with_services,
            name="Seed Org One - Servicio destacado",
        )
        fallback_announcement = Announcement.objects.get(
            organization=self.active_organization_without_services,
            name="Seed Org Two - Servicio destacado",
        )

        self.assertEqual(serviced_announcement.category, self.category)
        self.assertEqual(serviced_announcement.subservices.count(), 0)
        self.assertEqual(fallback_announcement.category.name, "General")
        self.assertEqual(fallback_announcement.subservices.count(), 0)
        self.assertIn("announcements_created=2", out.getvalue())

    def test_seed_announcements_is_idempotent(self):
        first_out = StringIO()
        second_out = StringIO()

        call_command("seed_announcements", stdout=first_out)
        call_command("seed_announcements", stdout=second_out)

        self.assertEqual(Announcement.objects.count(), 3)
        self.assertIn("announcements_created=0", second_out.getvalue())
        self.assertIn("announcements_updated=2", second_out.getvalue())


class SeedFixedTablesCommandTests(APITestCase):
    def test_seed_fixed_tables_creates_expected_catalog_data(self):
        out = StringIO()

        call_command("seed_fixed_tables", stdout=out)

        allowed_city_names = set(AllowedCity.objects.values_list("name", flat=True))
        seeded_category_names = set(
            Category.objects.filter(name__in={"Reformas", "Mantenimiento"}).values_list(
                "name", flat=True
            )
        )
        service_catalog_names = set(
            ServiceCatalog.objects.values_list("name", flat=True)
        )
        plan_tier_keys = list(
            PlanTierCatalog.objects.order_by("sort_order").values_list("key", flat=True)
        )
        feature_flags = {
            flag.key: flag.is_active for flag in FeatureFlag.objects.order_by("key")
        }

        self.assertEqual(len(allowed_city_names), 50)
        self.assertIn("Madrid", allowed_city_names)
        self.assertIn("València", allowed_city_names)
        self.assertIn("Vitoria-Gasteiz", allowed_city_names)
        self.assertEqual(seeded_category_names, {"Mantenimiento", "Reformas"})
        self.assertTrue(Category.objects.filter(name="General").exists())
        self.assertEqual(
            service_catalog_names,
            {"Electricidad", "Fontaneria", "Limpieza", "Pintura"},
        )
        self.assertEqual(plan_tier_keys, ["default", "premium", "pro", "ultra"])
        self.assertEqual(feature_flags, {})
        self.assertIn("allowed_cities_created=50", out.getvalue())
        self.assertIn("categories_created=2", out.getvalue())
        self.assertIn("plan_tiers_created=", out.getvalue())
        self.assertIn("service_catalogs_created=4", out.getvalue())
        self.assertIn("feature_flags_created=0", out.getvalue())


    def test_seed_fixed_tables_does_not_create_subservices(self):
        out = StringIO()

        call_command("seed_fixed_tables", stdout=out)

        self.assertEqual(Subservice.objects.count(), 0)
        self.assertIn("service_catalogs_created=4", out.getvalue())

    def test_seed_fixed_tables_is_idempotent_and_updates_existing_records(self):
        AllowedCity.objects.create(name="Madrid")
        plan_tier, _ = PlanTierCatalog.objects.update_or_create(
            key="default",
            defaults={
                "name": "Default antiguo",
                "description": "Descripcion antigua",
                "sort_order": 99,
            },
        )
        category = Category.objects.create(
            name="Reformas",
            description="Descripcion desactualizada",
        )
        mantenimiento = Category.objects.create(
            name="Mantenimiento",
            description="Otra descripcion desactualizada",
        )
        catalog = ServiceCatalog.objects.create(
            category=category,
            name="Pintura",
            description="Descripcion antigua",
        )
        FeatureFlag.objects.create(
            key="job_chat",
            name="Job chat antiguo",
            description="Descripcion antigua",
            is_active=False,
        )

        first_out = StringIO()
        second_out = StringIO()

        call_command("seed_fixed_tables", stdout=first_out)
        call_command("seed_fixed_tables", stdout=second_out)

        category.refresh_from_db()
        mantenimiento.refresh_from_db()
        catalog.refresh_from_db()
        plan_tier.refresh_from_db()

        self.assertEqual(AllowedCity.objects.count(), 50)
        self.assertEqual(PlanTierCatalog.objects.count(), 4)
        self.assertEqual(Category.objects.count(), 3)
        self.assertEqual(ServiceCatalog.objects.count(), 4)
        self.assertEqual(FeatureFlag.objects.count(), 1)

        self.assertEqual(plan_tier.name, "Default")
        self.assertEqual(
            plan_tier.description,
            "Tier base para organizaciones con configuracion estandar.",
        )
        self.assertEqual(plan_tier.sort_order, 10)
        self.assertEqual(
            category.description,
            "Servicios vinculados a reformas y obras.",
        )
        self.assertEqual(
            mantenimiento.description,
            "Servicios recurrentes de mantenimiento.",
        )
        self.assertEqual(catalog.category, category)
        self.assertEqual(
            catalog.description,
            "Trabajos de pintura interior y exterior.",
        )
        self.assertIn("plan_tiers_created=0", second_out.getvalue())
        self.assertIn("plan_tiers_updated=0", second_out.getvalue())
        self.assertIn("allowed_cities_created=0", second_out.getvalue())
        self.assertIn("allowed_cities_updated=0", second_out.getvalue())
        self.assertIn("categories_created=0", second_out.getvalue())
        self.assertIn("categories_updated=0", second_out.getvalue())
        self.assertIn("service_catalogs_created=0", second_out.getvalue())
        self.assertIn("service_catalogs_updated=0", second_out.getvalue())
        self.assertIn("feature_flags_created=0", second_out.getvalue())
        self.assertIn("feature_flags_updated=0", second_out.getvalue())


ADMIN_ENV = {
    "DJANGO_SUPERUSER_EMAIL": "admin@example.com",
    "DJANGO_SUPERUSER_PASSWORD": "test-admin-password",
}


class CreateAdminUserCommandTests(APITestCase):
    @mock.patch.dict(os.environ, ADMIN_ENV)
    def test_create_admin_user_creates_expected_superuser(self):
        out = StringIO()

        call_command("create_admin_user", stdout=out)

        user_model = get_user_model()
        admin_user = user_model.objects.get(email="admin@example.com")

        self.assertEqual(admin_user.username, "admin")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.check_password("test-admin-password"))
        self.assertIn("created", out.getvalue())

    @mock.patch.dict(os.environ, ADMIN_ENV)
    def test_create_admin_user_is_idempotent_and_repairs_admin_flags(self):
        user_model = get_user_model()
        admin_user = user_model.objects.create_user(
            username="custom-admin",
            email="admin@example.com",
            password="different-pass",
            is_staff=False,
            is_superuser=False,
        )
        out = StringIO()

        call_command("create_admin_user", stdout=out)

        admin_user.refresh_from_db()
        self.assertEqual(admin_user.username, "custom-admin")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.check_password("test-admin-password"))
        self.assertIn("updated", out.getvalue())

    def test_create_admin_user_requires_credentials_from_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(CommandError, "DJANGO_SUPERUSER_PASSWORD"):
                call_command("create_admin_user", stdout=StringIO())

        self.assertFalse(get_user_model().objects.filter(is_superuser=True).exists())

    @override_settings(IS_PRODUCTION=True)
    @mock.patch.dict(os.environ, ADMIN_ENV)
    def test_create_admin_user_refuses_to_run_in_production(self):
        with self.assertRaisesMessage(CommandError, "createsuperuser"):
            call_command("create_admin_user", stdout=StringIO())

        self.assertFalse(get_user_model().objects.filter(email="admin@example.com").exists())


class SeedCustomBulkCommandTests(APITestCase):
    def test_seed_custom_bulk_requires_seed_password(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(CommandError, "SEED_USER_PASSWORD"):
                call_command("seed_custom_bulk", stdout=StringIO())

        self.assertFalse(get_user_model().objects.exists())

    @override_settings(IS_PRODUCTION=True)
    @mock.patch.dict(os.environ, {"SEED_USER_PASSWORD": "seed-password"})
    def test_seed_custom_bulk_refuses_to_run_in_production(self):
        with self.assertRaisesMessage(CommandError, "production"):
            call_command("seed_custom_bulk", stdout=StringIO())


class ManagementAccessControlTests(APITestCase):
    """Every management endpoint must reject anonymous and non-staff callers."""

    PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"
    SCHEMALESS_URL_NAMES = (
        "management-stats",
        "management-assets-stats",
        "management-statistics-dashboard",
        "management-statistics-analytics-overview",
        "management-statistics-webstats",
    )

    def setUp(self):
        self.regular_user = get_user_model().objects.create_user(
            username="regular",
            email="regular@example.com",
            password="ChangeMe123!",
            email_verified=True,
        )

    def _operations(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        operations = set()
        for path, methods in schema["paths"].items():
            if not path.startswith("/api/management/"):
                continue
            concrete = re.sub(r"\{[^}]+\}", self.PLACEHOLDER_ID, path)
            operations.update((method, concrete) for method in methods if method != "parameters")
        # Plain APIViews without serializers are skipped by the schema generator.
        operations.update(("get", reverse(name)) for name in self.SCHEMALESS_URL_NAMES)
        self.assertGreater(len(operations), 50)
        return sorted(operations)

    def _assert_all(self, expected_status):
        for method, path in self._operations():
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, {}, format="json")
                self.assertEqual(response.status_code, expected_status)

    def test_anonymous_callers_are_rejected(self):
        self._assert_all(status.HTTP_401_UNAUTHORIZED)

    def test_non_staff_users_are_forbidden(self):
        self.client.force_authenticate(user=self.regular_user)
        self._assert_all(status.HTTP_403_FORBIDDEN)
