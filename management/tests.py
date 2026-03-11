from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from jobs.models import Job
from organization.models import Organization, Service, ServicePrice


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
        self.service = Service.objects.create(
            organization=self.organization,
            name="Managed Plan",
            description="",
        )
        self.service_price = ServicePrice.objects.create(
            service=self.service,
            amount="19.99",
            currency="EUR",
            effective_from=date(2026, 1, 1),
        )
        self.job = Job.objects.create(
            user=self.staff_candidate,
            organization=self.organization,
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
                "status": Organization.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Brand New Org")
        self.assertEqual(response.data["status"], Organization.Status.ACTIVE)

    def test_admin_can_suspend_job(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("management-jobs-suspend", kwargs={"uuid": self.job.uuid})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.SUSPENDED)

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
                "organization": str(self.organization.uuid),
                "plan_price": self.service_price.id,
                "status": Job.Status.ACTIVE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Job.Status.ACTIVE)
