from datetime import date
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.job_chat.models import JobChat, JobChatAttachment, JobChatMessage
from apps.jobs.models import Job
from apps.management.feature_flags import is_feature_enabled
from apps.management.models import FeatureFlag
from apps.organization.models import (
    Announcement,
    AnnouncementReview,
    Category,
    Organization,
    OrganizationJob,
    Service,
    ServicePrice,
    Subservice,
)


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
        self.organization_job = OrganizationJob.objects.create(
            organization=self.organization,
            name="Managed Services",
            description="Managed org job",
        )
        self.category, _ = Category.objects.get_or_create(
            name="Managed Category",
            defaults={"description": "Categoria gestionada"},
        )
        self.service = Service.objects.create(
            job=self.organization_job,
            category=self.category,
            name="Managed Plan",
            description="",
        )
        self.subservice = Subservice.objects.create(
            service=self.service,
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
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Managed Announcement",
            location="Madrid",
            announcement="Managed plan disponible",
        )
        self.announcement.services.add(self.service)
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

    def test_admin_can_suspend_job(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-jobs-suspend", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.SUSPENDED)

    def test_unauthenticated_user_cannot_deactivate_job(self):
        response = self.client.post(
            reverse("management-jobs-deactivate", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_staff_user_cannot_deactivate_job(self):
        self.client.force_authenticate(user=self.staff_candidate)

        response = self.client.post(
            reverse("management-jobs-deactivate", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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

    def test_admin_can_create_job(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-jobs-list"),
            {
                "user": str(self.staff_candidate.uuid),
                "announcement": str(self.announcement.uuid),
                "plan_price": self.service_price.id,
                "status": Job.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Job.Status.ACTIVE)


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
        self.assertEqual(Service.objects.count(), 4)
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
        self.assertEqual(Service.objects.count(), 4)
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
        self.organization_job = OrganizationJob.objects.create(
            organization=self.active_organization_with_services,
            name="Seed Job",
            description="Seed job",
        )
        self.service = Service.objects.create(
            job=self.organization_job,
            category=self.category,
            name="Seed Service",
            description="Seed service",
        )

    def test_seed_announcements_creates_one_announcement_per_active_organization(self):
        out = StringIO()

        call_command("seed_announcements", stdout=out)

        self.assertEqual(Announcement.objects.count(), 2)
        serviced_announcement = Announcement.objects.get(
            organization=self.active_organization_with_services,
            name="Seed Org One - Servicio destacado",
        )
        fallback_announcement = Announcement.objects.get(
            organization=self.active_organization_without_services,
            name="Seed Org Two - Servicio destacado",
        )

        self.assertEqual(serviced_announcement.category, self.category)
        self.assertEqual(list(serviced_announcement.services.all()), [self.service])
        self.assertEqual(fallback_announcement.category.name, "General")
        self.assertEqual(fallback_announcement.services.count(), 0)
        self.assertIn("announcements_created=2", out.getvalue())

    def test_seed_announcements_is_idempotent(self):
        first_out = StringIO()
        second_out = StringIO()

        call_command("seed_announcements", stdout=first_out)
        call_command("seed_announcements", stdout=second_out)

        self.assertEqual(Announcement.objects.count(), 2)
        self.assertIn("announcements_created=0", second_out.getvalue())
        self.assertIn("announcements_updated=2", second_out.getvalue())


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
