from django.urls import path

from .views import (
    ManagementStatisticsAnalyticsOverviewView,
    ManagementStatisticsDashboardView,
    ManagementStatisticsWebstatsView,
)

urlpatterns = [
    path("dashboard/", ManagementStatisticsDashboardView.as_view(), name="management-statistics-dashboard"),
    path(
        "analytics-overview/",
        ManagementStatisticsAnalyticsOverviewView.as_view(),
        name="management-statistics-analytics-overview",
    ),
    path("webstats/", ManagementStatisticsWebstatsView.as_view(), name="management-statistics-webstats"),
]
