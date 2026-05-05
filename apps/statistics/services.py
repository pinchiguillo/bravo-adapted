from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, models
from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.job_chat.models import JobChat, JobChatMessage
from apps.jobs.models import Job
from apps.organization.models import Announcement, AnnouncementFavorite, Organization

from .models import DailyAnnouncementStats, DailyPlatformStats

User = get_user_model()


@dataclass(frozen=True)
class Window:
    start: timezone.datetime.date
    end: timezone.datetime.date
    previous_start: timezone.datetime.date
    previous_end: timezone.datetime.date


def build_window(days: int = 30) -> Window:
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    return Window(
        start=start,
        end=end,
        previous_start=previous_start,
        previous_end=previous_end,
    )


def daterange(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def increment_announcement_view_stats(announcement_id: int, target_date=None) -> None:
    target_date = target_date or timezone.localdate()
    _increment_daily_platform_counter(target_date, "announcement_views", 1)
    _increment_daily_announcement_views(announcement_id, target_date, 1)


def _increment_daily_platform_counter(target_date, field_name: str, delta: int) -> None:
    updated = DailyPlatformStats.objects.filter(date=target_date).update(
        **{field_name: F(field_name) + delta}
    )
    if updated:
        return
    try:
        DailyPlatformStats.objects.create(date=target_date, **{field_name: delta})
    except IntegrityError:
        DailyPlatformStats.objects.filter(date=target_date).update(
            **{field_name: F(field_name) + delta}
        )


def _increment_daily_announcement_views(announcement_id: int, target_date, delta: int) -> None:
    updated = DailyAnnouncementStats.objects.filter(
        announcement_id=announcement_id,
        date=target_date,
    ).update(views=F("views") + delta)
    if updated:
        return
    try:
        DailyAnnouncementStats.objects.create(
            announcement_id=announcement_id,
            date=target_date,
            views=delta,
        )
    except IntegrityError:
        DailyAnnouncementStats.objects.filter(
            announcement_id=announcement_id,
            date=target_date,
        ).update(views=F("views") + delta)


def refresh_daily_platform_stats(start_date, end_date) -> None:
    if start_date > end_date:
        return

    new_users = _aggregate_daily_counts(User.objects, "date_joined", start_date, end_date)
    active_users = _aggregate_daily_counts(User.objects.exclude(last_login__isnull=True), "last_login", start_date, end_date)
    new_organizations = _aggregate_daily_counts(Organization.objects, "created_at", start_date, end_date)
    new_announcements = _aggregate_daily_counts(Announcement.objects, "created_at", start_date, end_date)
    announcement_favorites = _aggregate_daily_counts(AnnouncementFavorite.objects, "created_at", start_date, end_date)
    new_jobs = _aggregate_daily_counts(Job.objects, "created_at", start_date, end_date)
    new_job_chats = _aggregate_daily_counts(JobChat.objects, "created_at", start_date, end_date)
    new_job_chat_messages = _aggregate_daily_counts(JobChatMessage.objects, "created_at", start_date, end_date)

    for current_date in daterange(start_date, end_date):
        existing_views = (
            DailyPlatformStats.objects.filter(date=current_date)
            .values_list("announcement_views", flat=True)
            .first()
            or 0
        )
        DailyPlatformStats.objects.update_or_create(
            date=current_date,
            defaults={
                "new_users": new_users[current_date],
                "active_users": active_users[current_date],
                "new_organizations": new_organizations[current_date],
                "new_announcements": new_announcements[current_date],
                "announcement_favorites": announcement_favorites[current_date],
                "new_jobs": new_jobs[current_date],
                "new_job_chats": new_job_chats[current_date],
                "new_job_chat_messages": new_job_chat_messages[current_date],
                "announcement_views": existing_views,
            },
        )


def _aggregate_daily_counts(queryset, datetime_field: str, start_date, end_date):
    date_key = f"{datetime_field}__date"
    raw_rows = (
        queryset.filter(**{f"{datetime_field}__date__range": (start_date, end_date)})
        .values(date_key)
        .annotate(total=Count("pk"))
        .order_by()
    )
    counts = defaultdict(int)
    for row in raw_rows:
        counts[row[date_key]] = row["total"]
    return counts


def get_daily_platform_series(start_date, end_date):
    rows = {
        row.date: row
        for row in DailyPlatformStats.objects.filter(date__range=(start_date, end_date)).order_by("date")
    }
    return [
        {
            "date": current_date.isoformat(),
            "label": current_date.strftime("%d %b"),
            "new_users": rows.get(current_date).new_users if rows.get(current_date) else 0,
            "active_users": rows.get(current_date).active_users if rows.get(current_date) else 0,
            "new_announcements": rows.get(current_date).new_announcements if rows.get(current_date) else 0,
            "announcement_favorites": rows.get(current_date).announcement_favorites if rows.get(current_date) else 0,
            "new_jobs": rows.get(current_date).new_jobs if rows.get(current_date) else 0,
            "new_job_chats": rows.get(current_date).new_job_chats if rows.get(current_date) else 0,
            "new_job_chat_messages": rows.get(current_date).new_job_chat_messages if rows.get(current_date) else 0,
            "announcement_views": rows.get(current_date).announcement_views if rows.get(current_date) else 0,
        }
        for current_date in daterange(start_date, end_date)
    ]


def get_dashboard_payload(days: int = 30):
    window = build_window(days)
    series = get_daily_platform_series(window.start, window.end)
    return {
        "window_days": days,
        "kpis": {
            "users_total": User.objects.count(),
            "users_active_30d": User.objects.filter(last_login__date__gte=window.start).count(),
            "organizations_total": Organization.objects.count(),
            "announcements_total": Announcement.objects.count(),
        },
        "series": {
            "announcement_views": [
                {"date": row["date"], "label": row["label"], "value": row["announcement_views"]}
                for row in series
            ],
        },
        "recent_activity": {
            "new_users": sum(row["new_users"] for row in series),
            "new_announcements": sum(row["new_announcements"] for row in series),
            "new_jobs": sum(row["new_jobs"] for row in series),
            "new_messages": sum(row["new_job_chat_messages"] for row in series),
        },
        "top_announcements": get_top_announcements(window.start, window.end, limit=5),
    }


def get_analytics_overview_payload(days: int = 30):
    window = build_window(days)
    current_totals = get_platform_window_totals(window.start, window.end)
    previous_totals = get_platform_window_totals(window.previous_start, window.previous_end)
    series = get_daily_platform_series(window.start, window.end)
    return {
        "window_days": days,
        "kpis": {
            "announcement_views": _metric_with_delta(
                current_totals["announcement_views"],
                previous_totals["announcement_views"],
            ),
            "active_users": _metric_with_delta(
                User.objects.filter(last_login__date__gte=window.start).count(),
                User.objects.filter(
                    last_login__date__range=(window.previous_start, window.previous_end)
                ).count(),
            ),
            "new_announcements": _metric_with_delta(
                current_totals["new_announcements"],
                previous_totals["new_announcements"],
            ),
            "favorites": _metric_with_delta(
                current_totals["announcement_favorites"],
                previous_totals["announcement_favorites"],
            ),
            "jobs": _metric_with_delta(
                current_totals["new_jobs"],
                previous_totals["new_jobs"],
            ),
            "messages": _metric_with_delta(
                current_totals["new_job_chat_messages"],
                previous_totals["new_job_chat_messages"],
            ),
        },
        "series": series,
        "funnel": [
            {"label": "Visitas", "value": current_totals["announcement_views"]},
            {"label": "Favoritos", "value": current_totals["announcement_favorites"]},
            {"label": "Jobs", "value": current_totals["new_jobs"]},
            {"label": "Chats", "value": current_totals["new_job_chats"]},
            {"label": "Mensajes", "value": current_totals["new_job_chat_messages"]},
        ],
        "top_announcements": get_top_announcements(window.start, window.end, limit=5),
        "top_categories": get_top_categories(window.start, window.end, limit=5),
        "top_locations": get_top_locations(window.start, window.end, limit=5),
    }


def get_webstats_payload(days: int = 30):
    window = build_window(days)
    current_totals = get_platform_window_totals(window.start, window.end)
    previous_totals = get_platform_window_totals(window.previous_start, window.previous_end)
    return {
        "window_days": days,
        "kpis": {
            "new_users": _metric_with_delta(
                current_totals["new_users"],
                previous_totals["new_users"],
            ),
            "active_users": _metric_with_delta(
                User.objects.filter(last_login__date__gte=window.start).count(),
                User.objects.filter(
                    last_login__date__range=(window.previous_start, window.previous_end)
                ).count(),
            ),
            "announcement_views": _metric_with_delta(
                current_totals["announcement_views"],
                previous_totals["announcement_views"],
            ),
            "favorites": _metric_with_delta(
                current_totals["announcement_favorites"],
                previous_totals["announcement_favorites"],
            ),
        },
        "series": get_daily_platform_series(window.start, window.end),
        "top_announcements": get_top_announcements(window.start, window.end, limit=8),
        "top_categories": get_top_categories(window.start, window.end, limit=6),
        "top_locations": get_top_locations(window.start, window.end, limit=6),
        "engagement": {
            "jobs": current_totals["new_jobs"],
            "chats": current_totals["new_job_chats"],
            "messages": current_totals["new_job_chat_messages"],
        },
    }


def get_platform_window_totals(start_date, end_date):
    totals = (
        DailyPlatformStats.objects.filter(date__range=(start_date, end_date)).aggregate(
            new_users=Sum("new_users"),
            active_users=Sum("active_users"),
            new_announcements=Sum("new_announcements"),
            announcement_favorites=Sum("announcement_favorites"),
            new_jobs=Sum("new_jobs"),
            new_job_chats=Sum("new_job_chats"),
            new_job_chat_messages=Sum("new_job_chat_messages"),
            announcement_views=Sum("announcement_views"),
        )
    )
    return {key: value or 0 for key, value in totals.items()}


def get_top_announcements(start_date, end_date, limit: int = 5):
    views_by_announcement = {
        row["announcement_id"]: row["total_views"]
        for row in DailyAnnouncementStats.objects.filter(date__range=(start_date, end_date))
        .values("announcement_id")
        .annotate(total_views=Sum("views"))
    }
    favorites_by_announcement = {
        row["announcement_id"]: row["total_favorites"]
        for row in AnnouncementFavorite.objects.filter(
            created_at__date__range=(start_date, end_date)
        )
        .values("announcement_id")
        .annotate(total_favorites=Count("pk"))
    }
    jobs_by_announcement = {
        row["announcement_id"]: row["total_jobs"]
        for row in Job.objects.filter(created_at__date__range=(start_date, end_date))
        .values("announcement_id")
        .annotate(total_jobs=Count("pk"))
    }
    announcement_ids = set(views_by_announcement) | set(favorites_by_announcement) | set(jobs_by_announcement)
    rows = Announcement.objects.select_related("organization", "category").filter(
        models.Q(id__in=announcement_ids) | models.Q(view_count__gt=0)
    )
    ranked_rows = sorted(
        rows,
        key=lambda row: (
            views_by_announcement.get(row.id, 0),
            favorites_by_announcement.get(row.id, 0),
            jobs_by_announcement.get(row.id, 0),
            row.view_count,
        ),
        reverse=True,
    )[:limit]
    payload = []
    for row in ranked_rows:
        recent_views = views_by_announcement.get(row.id, 0)
        recent_favorites = favorites_by_announcement.get(row.id, 0)
        recent_jobs = jobs_by_announcement.get(row.id, 0)
        if not (recent_views or recent_favorites or recent_jobs or row.view_count):
            continue
        payload.append(
            {
                "uuid": str(row.uuid),
                "name": row.name,
                "organization_name": row.organization.name,
                "location": row.location,
                "category_name": row.category.name,
                "lifetime_views": row.view_count,
                "recent_views": recent_views,
                "recent_favorites": recent_favorites,
                "recent_jobs": recent_jobs,
            }
        )
    return payload


def get_top_categories(start_date, end_date, limit: int = 5):
    rows_by_name = {}
    for row in (
        Announcement.objects.values("category__name")
        .annotate(announcement_count=Count("id"))
        .order_by()
    ):
        rows_by_name[row["category__name"]] = {
            "name": row["category__name"],
            "announcement_count": row["announcement_count"],
            "recent_views": 0,
            "recent_jobs": 0,
        }
    for row in (
        DailyAnnouncementStats.objects.filter(date__range=(start_date, end_date))
        .values("announcement__category__name")
        .annotate(recent_views=Sum("views"))
        .order_by()
    ):
        rows_by_name.setdefault(
            row["announcement__category__name"],
            {
                "name": row["announcement__category__name"],
                "announcement_count": 0,
                "recent_views": 0,
                "recent_jobs": 0,
            },
        )["recent_views"] = row["recent_views"] or 0
    for row in (
        Job.objects.filter(created_at__date__range=(start_date, end_date))
        .values("announcement__category__name")
        .annotate(recent_jobs=Count("pk"))
        .order_by()
    ):
        rows_by_name.setdefault(
            row["announcement__category__name"],
            {
                "name": row["announcement__category__name"],
                "announcement_count": 0,
                "recent_views": 0,
                "recent_jobs": 0,
            },
        )["recent_jobs"] = row["recent_jobs"] or 0
    ranked = sorted(
        rows_by_name.values(),
        key=lambda row: (
            row["recent_views"],
            row["recent_jobs"],
            row["announcement_count"],
            row["name"],
        ),
        reverse=True,
    )[:limit]
    return [
        {
            "name": row["name"],
            "announcement_count": row["announcement_count"],
            "recent_views": row["recent_views"],
            "recent_jobs": row["recent_jobs"],
        }
        for row in ranked
        if row["announcement_count"] or row["recent_views"] or row["recent_jobs"]
    ]


def get_top_locations(start_date, end_date, limit: int = 5):
    rows_by_name = {}
    for row in Announcement.objects.values("location").annotate(announcement_count=Count("id")).order_by():
        rows_by_name[row["location"] or "Sin ubicación"] = {
            "name": row["location"] or "Sin ubicación",
            "announcement_count": row["announcement_count"],
            "recent_views": 0,
            "recent_jobs": 0,
        }
    for row in (
        DailyAnnouncementStats.objects.filter(date__range=(start_date, end_date))
        .values("announcement__location")
        .annotate(recent_views=Sum("views"))
        .order_by()
    ):
        key = row["announcement__location"] or "Sin ubicación"
        rows_by_name.setdefault(
            key,
            {
                "name": key,
                "announcement_count": 0,
                "recent_views": 0,
                "recent_jobs": 0,
            },
        )["recent_views"] = row["recent_views"] or 0
    for row in (
        Job.objects.filter(created_at__date__range=(start_date, end_date))
        .values("announcement__location")
        .annotate(recent_jobs=Count("pk"))
        .order_by()
    ):
        key = row["announcement__location"] or "Sin ubicación"
        rows_by_name.setdefault(
            key,
            {
                "name": key,
                "announcement_count": 0,
                "recent_views": 0,
                "recent_jobs": 0,
            },
        )["recent_jobs"] = row["recent_jobs"] or 0
    ranked = sorted(
        rows_by_name.values(),
        key=lambda row: (
            row["recent_views"],
            row["recent_jobs"],
            row["announcement_count"],
            row["name"],
        ),
        reverse=True,
    )[:limit]
    return [
        {
            "name": row["name"],
            "announcement_count": row["announcement_count"],
            "recent_views": row["recent_views"],
            "recent_jobs": row["recent_jobs"],
        }
        for row in ranked
    ]


def _metric_with_delta(current: int, previous: int):
    return {
        "value": current,
        "previous_value": previous,
        "delta_percentage": _percent_delta(current, previous),
    }


def _percent_delta(current: int, previous: int):
    if previous == 0:
        if current == 0:
            return 0.0
        return None
    return round(((current - previous) / previous) * 100, 1)
