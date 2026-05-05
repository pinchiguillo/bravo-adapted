from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsActiveAccount

from .services import (
    get_analytics_overview_payload,
    get_dashboard_payload,
    get_webstats_payload,
)


class StatisticsManagementViewMixin:
    permission_classes = [IsActiveAccount, permissions.IsAdminUser]

    def get_permissions(self):
        if settings.BYPASS_ADMIN_LOGIN:
            return [permissions.AllowAny()]
        return super().get_permissions()


@extend_schema(tags=["Management / Statistics"])
class ManagementStatisticsDashboardView(StatisticsManagementViewMixin, APIView):
    @extend_schema(summary="Get dashboard statistics")
    def get(self, request):
        return Response(get_dashboard_payload())


@extend_schema(tags=["Management / Statistics"])
class ManagementStatisticsAnalyticsOverviewView(StatisticsManagementViewMixin, APIView):
    @extend_schema(summary="Get analytics overview statistics")
    def get(self, request):
        return Response(get_analytics_overview_payload())


@extend_schema(tags=["Management / Statistics"])
class ManagementStatisticsWebstatsView(StatisticsManagementViewMixin, APIView):
    @extend_schema(summary="Get webstats statistics")
    def get(self, request):
        return Response(get_webstats_payload())
