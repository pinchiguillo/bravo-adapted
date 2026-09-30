from datetime import date, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.job_chat.models import JobChat, JobChatMessage
from apps.jobs.models import Job
from apps.organization.models import (
    Announcement,
    AnnouncementFavorite,
    Category,
    Organization,
)

from .models import DailyAnnouncementStats, DailyPlatformStats


class StatisticsApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            username="statistics-admin",
            email="statistics-admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="statistics-regular",
            email="statistics-regular@example.com",
            password="testpass123",
        )
        self.provider_user = user_model.objects.create_user(
            username="statistics-provider",
            email="statistics-provider@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.provider_user,
            name="Statistics Org",
            legal_name="Statistics Org SL",
            tax_id="ST123",
            billing_email="billing@statistics.example.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
            is_approved=True,
        )
        self.category = Category.objects.create(
            name="Photography",
            description="Photography services",
        )
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Wedding Photos",
            location="Madrid",
            announcement="Photography package",
            description="Full day photo package",
            free_text="Available weekends",
            status=Announcement.Status.ACTIVE,
            view_count=12,
        )
        self.favorite = AnnouncementFavorite.objects.create(
            user=self.regular_user,
            announcement=self.announcement,
        )
        self.job = Job.objects.create(
            user=self.regular_user,
            announcement=self.announcement,
            status=Job.Status.ACTIVE,
        )
        self.chat = JobChat.objects.create(job=self.job)
        self.message = JobChatMessage.objects.create(
            job_chat=self.chat,
            user=self.regular_user,
            content="Interested in booking",
        )
        today = date.today()
        yesterday = today - timedelta(days=1)
        DailyPlatformStats.objects.create(
            date=yesterday,
            new_users=1,
            active_users=1,
            new_announcements=1,
            announcement_favorites=1,
            new_jobs=1,
            new_job_chats=1,
            new_job_chat_messages=1,
            announcement_views=3,
        )
        DailyPlatformStats.objects.create(
            date=today,
            new_users=2,
            active_users=2,
            new_organizations=1,
            new_announcements=1,
            announcement_favorites=1,
            new_jobs=1,
            new_job_chats=1,
            new_job_chat_messages=1,
            announcement_views=7,
        )
        DailyAnnouncementStats.objects.create(
            announcement=self.announcement,
            date=yesterday,
            views=3,
        )
        DailyAnnouncementStats.objects.create(
            announcement=self.announcement,
            date=today,
            views=7,
        )

    def test_dashboard_endpoint_returns_real_payload(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-statistics-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["kpis"]["organizations_total"], 1)
        self.assertEqual(response.data["recent_activity"]["new_jobs"], 2)
        self.assertEqual(response.data["top_announcements"][0]["uuid"], str(self.announcement.uuid))

    def test_analytics_overview_endpoint_returns_funnel_and_rankings(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-statistics-analytics-overview"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["funnel"][0]["label"], "Visitas")
        self.assertEqual(response.data["top_categories"][0]["name"], self.category.name)
        self.assertEqual(response.data["top_locations"][0]["name"], self.announcement.location)

    def test_webstats_endpoint_returns_engagement_and_top_announcements(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("management-statistics-webstats"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["engagement"]["jobs"], 2)
        self.assertEqual(response.data["top_announcements"][0]["recent_views"], 10)

    def test_non_admin_cannot_access_statistics_endpoints(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("management-statistics-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class StatisticsCommandsTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="command-user",
            email="command-user@example.com",
            password="testpass123",
        )
        self.user.date_joined = self.user.date_joined.replace(hour=10)
        self.user.save(update_fields=["date_joined"])
        self.user.last_login = self.user.date_joined
        self.user.save(update_fields=["last_login"])
        self.provider_user = user_model.objects.create_user(
            username="command-provider",
            email="command-provider@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            user=self.provider_user,
            name="Command Org",
            legal_name="Command Org SL",
            tax_id="CMD123",
            billing_email="billing@command.example.com",
            billing_address="Main 1",
            billing_city="Madrid",
            billing_country="ES",
            billing_postal_code="28001",
        )
        self.category = Category.objects.create(name="Music", description="Music services")
        self.announcement = Announcement.objects.create(
            organization=self.organization,
            category=self.category,
            name="Live Band",
            location="Sevilla",
            announcement="Live show",
            description="Band for events",
            free_text="Available every month",
            status=Announcement.Status.ACTIVE,
        )
        AnnouncementFavorite.objects.create(user=self.user, announcement=self.announcement)
        self.job = Job.objects.create(user=self.user, announcement=self.announcement)
        self.chat = JobChat.objects.create(job=self.job)
        JobChatMessage.objects.create(
            job_chat=self.chat,
            user=self.user,
            content="Need pricing",
        )

    def test_backfill_daily_stats_command_is_idempotent(self):
        target_date = self.user.date_joined.date().isoformat()
        stdout = StringIO()

        call_command("backfill_daily_stats", "--from", target_date, "--to", target_date, stdout=stdout)
        call_command("backfill_daily_stats", "--from", target_date, "--to", target_date, stdout=stdout)

        stats = DailyPlatformStats.objects.get(date=self.user.date_joined.date())
        self.assertEqual(stats.new_users, 2)
        self.assertEqual(stats.active_users, 1)
        self.assertEqual(stats.new_announcements, 1)
        self.assertEqual(stats.announcement_favorites, 1)
        self.assertEqual(stats.new_jobs, 1)
        self.assertEqual(stats.new_job_chats, 1)
        self.assertEqual(stats.new_job_chat_messages, 1)

    @override_settings(USE_TZ=True)
    def test_refresh_daily_stats_command_refreshes_recent_window(self):
        call_command("refresh_daily_stats", "--days", "1")

        self.assertTrue(DailyPlatformStats.objects.filter(date=date.today()).exists())
