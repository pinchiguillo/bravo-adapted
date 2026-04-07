from datetime import date
from io import StringIO
from unittest import skipUnless

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.management.feature_flags import is_feature_enabled
from apps.management.models import FeatureFlag
from apps.organization.models import (
    AllowedCity,
    Announcement,
    AnnouncementReview,
    Category,
    Organization,
    ServiceCatalog,
    ServicePrice,
    Subservice,
)

JOBS_INSTALLED = django_apps.is_installed("apps.jobs")
JOB_CHAT_INSTALLED = django_apps.is_installed("apps.job_chat")

if JOBS_INSTALLED:
    from apps.jobs.models import Job
else:
    Job = None

if JOB_CHAT_INSTALLED:
    from apps.job_chat.models import JobChat, JobChatAttachment, JobChatMessage
else:
    JobChat = None
    JobChatAttachment = None
    JobChatMessage = None


@skipUnless(JOBS_INSTALLED, "jobs app disabled")
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
            billing_email="billing@managed-org.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
        )
        if JOBS_INSTALLED:
            self.category, _ = Category.objects.get_or_create(
                name="Managed Category",
                defaults={"description": "Categoria gestionada"},
            )
            self.announcement = Announcement.objects.create(
                organization=self.organization,
                category=self.category,
                name="Managed Announcement",
                location="Madrid",
                announcement="Managed plan disponible",
            )
            self.service_catalog = ServiceCatalog.objects.create(
                category=self.category,
                name="Managed Plan",
                description="",
            )
            self.subservice = Subservice.objects.create(
                announcement=self.announcement,
                service_catalog=self.service_catalog,
                name="Managed Variant",
                description="",
            )
            self.service_price = ServicePrice.objects.create(
                subservice=self.subservice,
                amount="19.99",
                currency="EUR",
                charging_type=ServicePrice.ChargingType.PER_PROJECT,
                effective_from=date(2026, 1, 1),
            )
            self.job = Job.objects.create(
                user=self.staff_candidate,
                announcement=self.announcement,
                plan_price=self.service_price,
                status=Job.Status.PENDING,
            )

    def test_non_staff_cannot_access_management_endpoints(self):
        self.client.force_authenticate(user=self.staff_candidate)

        response = self.client.get(reverse("management-users-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
                "billing_email": "billing@brand-new-org.com",
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
                "billing_email": "billing@duplicate-managed-org.com",
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

    @skipUnless(JOBS_INSTALLED, "jobs app disabled")
    def test_admin_can_suspend_job(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-jobs-suspend", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.SUSPENDED)


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
            billing_email="billing@announcements-org.com",
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

    @skipUnless(JOBS_INSTALLED, "jobs app disabled")
    def test_unauthenticated_user_cannot_deactivate_job(self):
        response = self.client.post(
            reverse("management-jobs-deactivate", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(BYPASS_ADMIN_LOGIN=True)
    def test_bypass_admin_login_allows_unauthenticated_access_to_management_list(self):
        response = self.client.get(reverse("management-users-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertNotIn("id", response.data["results"][0])

    @skipUnless(JOBS_INSTALLED, "jobs app disabled")
    @override_settings(BYPASS_ADMIN_LOGIN=True)
    def test_bypass_admin_login_allows_unauthenticated_management_status_actions(self):
        response = self.client.post(
            reverse("management-jobs-deactivate", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.INACTIVE)

    @skipUnless(JOBS_INSTALLED, "jobs app disabled")
    def test_non_staff_user_cannot_deactivate_job(self):
        self.client.force_authenticate(user=self.staff_candidate)

        response = self.client.post(
            reverse("management-jobs-deactivate", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @skipUnless(JOBS_INSTALLED, "jobs app disabled")
    def test_suspended_admin_cannot_activate_job(self):
        self.admin_user.status = self.admin_user.Status.SUSPENDED
        self.admin_user.save(update_fields=["status"])
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-jobs-activate", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_suspended_admin_cannot_access_management_endpoints(self):
        self.admin_user.status = self.admin_user.Status.SUSPENDED
        self.admin_user.save(update_fields=["status"])
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-users-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @skipUnless(JOBS_INSTALLED, "jobs app disabled")
    def test_admin_can_create_job(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-jobs-list"),
            {
                "user": str(self.staff_candidate.uuid),
                "announcement": str(self.announcement.uuid),
                "plan_price": str(self.service_price.uuid),
                "status": Job.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Job.Status.ACTIVE)
        self.assertNotIn("id", response.data)


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
            billing_email="billing@managed-list-org.com",
            billing_address="Main 10",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28010",
        )

    def test_admin_can_list_organizations_from_management_endpoint(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-organizations-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.organization.uuid))


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


@skipUnless(JOBS_INSTALLED, "jobs app disabled")
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    MEDIA_ROOT="/tmp/bravo-management-seed-tests-media",
    MEDIA_URL="/media/",
)
class SeedDemoDataCommandJobChatDisabledTests(APITestCase):
    def test_seed_demo_data_skips_job_chat_records_when_feature_is_disabled(self):
        out = StringIO()

        call_command("seed_demo_data", stdout=out)

        self.assertEqual(Job.objects.count(), 4)
        self.assertFalse(JOB_CHAT_INSTALLED)
        self.assertIn("job_chats=0", out.getvalue())
        self.assertIn("job_chat_messages=0", out.getvalue())
        self.assertIn("job_chat_attachments=0", out.getvalue())


@skipUnless(JOBS_INSTALLED, "jobs app disabled")
@skipUnless(JOB_CHAT_INSTALLED, "job_chat app disabled")
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    MEDIA_ROOT="/tmp/bravo-management-seed-tests-media",
    MEDIA_URL="/media/",
)
class SeedDemoDataCommandTests(APITestCase):
    def test_seed_demo_data_creates_expected_records_and_passwords(self):
        out = StringIO()

        call_command("seed_demo_data", stdout=out)

        user_model = get_user_model()
        self.assertEqual(user_model.objects.count(), 4)
        self.assertEqual(Organization.objects.count(), 2)
        self.assertEqual(ServiceCatalog.objects.count(), 4)
        self.assertEqual(Subservice.objects.count(), 8)
        self.assertEqual(ServicePrice.objects.count(), 8)
        seeded_category_names = set(
            Category.objects.filter(name__in={"Reformas", "Mantenimiento"}).values_list(
                "name", flat=True
            )
        )
        self.assertEqual(seeded_category_names, {"Reformas", "Mantenimiento"})
        self.assertEqual(Announcement.objects.count(), 2)
        self.assertEqual(AnnouncementReview.objects.count(), 2)
        self.assertEqual(Job.objects.count(), 4)
        self.assertEqual(JobChat.objects.count(), 4)
        self.assertEqual(JobChatMessage.objects.count(), 6)
        self.assertEqual(JobChatAttachment.objects.count(), 1)
        self.assertEqual(Organization.objects.filter(is_approved=True).count(), 1)
        self.assertEqual(Organization.objects.filter(is_approved=False).count(), 1)
        self.assertFalse(settings.RGPD_MODULE_ENABLED)

        seeded_user = user_model.objects.get(email="ana.client@example.com")
        self.assertTrue(seeded_user.check_password("change-me-admin-password"))
        self.assertIn("Seed completed", out.getvalue())
        self.assertIn("categories=2", out.getvalue())
        self.assertIn("job_chat_attachments=1", out.getvalue())
        self.assertIn("rgpd_anonymous_consent_events=0", out.getvalue())

    def test_seed_demo_data_is_idempotent(self):
        first_out = StringIO()
        second_out = StringIO()

        call_command("seed_demo_data", stdout=first_out)
        call_command("seed_demo_data", stdout=second_out)

        user_model = get_user_model()
        self.assertEqual(user_model.objects.count(), 4)
        self.assertEqual(Organization.objects.count(), 2)
        self.assertEqual(ServiceCatalog.objects.count(), 4)
        self.assertEqual(Subservice.objects.count(), 8)
        self.assertEqual(ServicePrice.objects.count(), 8)
        seeded_category_names = set(
            Category.objects.filter(name__in={"Reformas", "Mantenimiento"}).values_list(
                "name", flat=True
            )
        )
        self.assertEqual(seeded_category_names, {"Reformas", "Mantenimiento"})
        self.assertEqual(Announcement.objects.count(), 2)
        self.assertEqual(AnnouncementReview.objects.count(), 2)
        self.assertEqual(Job.objects.count(), 4)
        self.assertEqual(JobChat.objects.count(), 4)
        self.assertEqual(JobChatMessage.objects.count(), 6)
        self.assertEqual(JobChatAttachment.objects.count(), 1)
        self.assertEqual(Organization.objects.filter(is_approved=True).count(), 1)
        self.assertEqual(Organization.objects.filter(is_approved=False).count(), 1)
        self.assertIn("created=0", second_out.getvalue())
        self.assertIn("rgpd_consents=0", second_out.getvalue())


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
        self.assertEqual(
            feature_flags,
            {
                "job_chat": True,
                "job_chat_attachments": True,
                "job_chat_uploads": True,
            },
        )
        self.assertIn("allowed_cities_created=50", out.getvalue())
        self.assertIn("categories_created=2", out.getvalue())
        self.assertIn("service_catalogs_created=4", out.getvalue())
        self.assertIn("feature_flags_created=3", out.getvalue())

    def test_seed_fixed_tables_does_not_create_subservices(self):
        out = StringIO()

        call_command("seed_fixed_tables", stdout=out)

        self.assertEqual(Subservice.objects.count(), 0)
        self.assertIn("service_catalogs_created=4", out.getvalue())

    def test_seed_fixed_tables_is_idempotent_and_updates_existing_records(self):
        AllowedCity.objects.create(name="Madrid")
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
        job_chat_flag = FeatureFlag.objects.get(key="job_chat")

        self.assertEqual(AllowedCity.objects.count(), 50)
        self.assertEqual(Category.objects.count(), 3)
        self.assertEqual(ServiceCatalog.objects.count(), 4)
        self.assertEqual(FeatureFlag.objects.count(), 3)
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
        self.assertTrue(job_chat_flag.is_active)
        self.assertEqual(job_chat_flag.name, "Job chat")
        self.assertIn("allowed_cities_created=0", second_out.getvalue())
        self.assertIn("allowed_cities_updated=0", second_out.getvalue())
        self.assertIn("categories_created=0", second_out.getvalue())
        self.assertIn("categories_updated=0", second_out.getvalue())
        self.assertIn("service_catalogs_created=0", second_out.getvalue())
        self.assertIn("service_catalogs_updated=0", second_out.getvalue())
        self.assertIn("feature_flags_created=0", second_out.getvalue())
        self.assertIn("feature_flags_updated=0", second_out.getvalue())


class CreateAdminUserCommandTests(APITestCase):
    def test_create_admin_user_creates_expected_superuser(self):
        out = StringIO()

        call_command("create_admin_user", stdout=out)

        user_model = get_user_model()
        admin_user = user_model.objects.get(email="admin@bravo.example.com")

        self.assertEqual(admin_user.username, "admin")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.check_password("change-me-admin-password"))
        self.assertIn("created", out.getvalue())

    def test_create_admin_user_is_idempotent_and_repairs_admin_flags(self):
        user_model = get_user_model()
        admin_user = user_model.objects.create_user(
            username="custom-admin",
            email="admin@bravo.example.com",
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
        self.assertTrue(admin_user.check_password("change-me-admin-password"))
        self.assertIn("updated", out.getvalue())
