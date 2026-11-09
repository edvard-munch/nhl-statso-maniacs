"""Read saved scheduling evidence; never initialize state or probe services."""

from datetime import datetime, time, timedelta, timezone as utc

from django.conf import settings
from nhl_web_app.celery_schedule import SECONDS_PER_DAY
from django.db.models import Exists, OuterRef, Q

from . import loader_runs, scheduler
from .models import Game, LoaderRun, LoaderScheduleState

DEFAULT_GRACE_SECONDS = 900
DEFAULT_MAX_RUN_SECONDS = 3600
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_LIMIT = 20
MAX_LIMIT = 1000
DAYS_PER_WEEK = 7
MAX_THRESHOLD_SECONDS = DAYS_PER_WEEK * SECONDS_PER_DAY
MAX_LOOKBACK_HOURS = 30 * 24
SCHEMA_VERSION = 1


def _job(last, due_at, overdue_at, now):
    return {
        "last_success": last,
        "due_at": due_at if last is not None else None,
        "overdue_at": overdue_at if last is not None else None,
        "missing": last is None,
        "due": last is None or now >= due_at,
        "overdue": last is not None and now > overdue_at,
    }


def _maintenance(state, options, now, grace, near):
    day = now.date()
    start_time = time(hour=options["quiet_start_hour"], tzinfo=utc.utc)
    start = datetime.combine(day, start_time)
    if now < start:
        start -= timedelta(days=1)
    window = timedelta(hours=options["quiet_hours"])
    # A crossing-midnight window belongs to the date on which it starts.
    expected_start = start
    while now <= expected_start + window + grace:
        expected_start -= timedelta(days=1)
    last_daily = state.daily_completed_date if state else None
    last_weekly = state.weekly_completed_date if state else None
    daily_due = (
        datetime.combine(last_daily + timedelta(days=1), start_time) if last_daily else start
    )
    daily = _job(last_daily, daily_due, daily_due + window + grace, now)
    daily["overdue"] = last_daily is not None and last_daily < expected_start.date()
    week = day - timedelta(days=now.weekday())
    weekly_start = datetime.combine(week + timedelta(days=options["weekly_weekday"]), start_time)
    last_weekly_window = weekly_start
    while now <= last_weekly_window + window + grace:
        last_weekly_window -= timedelta(days=DAYS_PER_WEEK)
    expected_week = last_weekly_window.date() - timedelta(days=options["weekly_weekday"])
    weekly_due = (
        datetime.combine(
            last_weekly
            - timedelta(days=last_weekly.weekday())
            + timedelta(days=DAYS_PER_WEEK + options["weekly_weekday"]),
            start_time,
        )
        if last_weekly
        else weekly_start
    )
    weekly = _job(last_weekly, weekly_due, weekly_due + window + grace, now)
    weekly["overdue"] = last_weekly is not None and last_weekly < expected_week
    eligible = start <= now < start + window and not near
    for job in (daily, weekly):
        job["eligible_now"] = eligible and job["due"]
        job["blocked_by"] = (
            "active_or_imminent_games"
            if near
            else "outside_quiet_window"
            if not start <= now < start + window
            else None
        )
    return {"daily": daily, "weekly": weekly}


def _games(now, options, grace, limit):
    result = {}
    for final, name in ((False, "live"), (True, "final")):
        candidates = list(
            scheduler.game_candidates(now, final=final, due_only=False).order_by(
                "starts_at", "game_id"
            )
        )
        saved = {
            game.nhl_id: game
            for game in Game.objects.filter(nhl_id__in=[item.game_id for item in candidates])
        }
        interval = timedelta(seconds=options[name + "_seconds"])
        rows = []
        for item in candidates:
            attempted = item.last_final_attempt_at if final else item.last_live_attempt_at
            origin = item.first_final_seen_at if final else item.starts_at
            game = saved.get(item.game_id)
            published = game.updated_date if game else None
            # An old live publication does not make a newly discovered final
            # immediately overdue; its final reconciliation gets its own grace.
            reference = max(origin, published) if published else origin
            row = {
                "game_id": item.game_id,
                "last_attempt_at": attempted,
                "saved_at": published,
                "saved_game_finished": game.game_finished if game else None,
                "due_at": attempted + interval if attempted else origin,
                "overdue_at": reference + interval + grace,
            }
            row["due"] = attempted is None or now >= row["due_at"]
            row["overdue"] = now > row["overdue_at"]
            rows.append(row)
        # Unhealthy rows must not be hidden behind a healthy display limit.
        rows.sort(key=lambda row: (not row["overdue"], not row["due"], row["game_id"]))
        result[name] = {
            "eligible_count": len(rows),
            "due_count": sum(row["due"] for row in rows),
            "overdue_count": sum(row["overdue"] for row in rows),
            "games": rows[:limit],
            "truncated": len(rows) > limit,
        }
    return result


def report(
    now,
    *,
    grace_seconds=DEFAULT_GRACE_SECONDS,
    max_run_seconds=DEFAULT_MAX_RUN_SECONDS,
    lookback_hours=DEFAULT_LOOKBACK_HOURS,
    limit=DEFAULT_LIMIT,
):
    now = now.astimezone(utc.utc)
    options = settings.NHL_SCHEDULING
    result = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now,
        "enabled": options["enabled"],
        "status": "disabled" if not options["enabled"] else "healthy",
        "scope": "saved_database_state_only",
        "services_checked": False,
        "thresholds": {
            "grace_seconds": grace_seconds,
            "max_run_seconds": max_run_seconds,
            "failure_lookback_hours": lookback_hours,
            "display_limit": limit,
        },
        "schedule": dict(options),
        "issues": [],
    }
    if not options["enabled"]:
        return result
    state = LoaderScheduleState.objects.filter(pk=loader_runs.SCHEDULE_STATE_KEY).first()
    grace = timedelta(seconds=grace_seconds)
    near = scheduler.near_games(now)
    interval = options["discovery_seconds" if near else "quiet_discovery_seconds"]
    discovered = state.discovered_at if state else None
    due = discovered + timedelta(seconds=interval) if discovered else now
    jobs = {
        "discovery": _job(discovered, due, due + grace, now),
        **_maintenance(state, options, now, grace, near),
        **_games(now, options, grace, limit),
    }
    result.update(
        jobs=jobs,
        cooldown_until=state.cooldown_until if state else None,
        cooldown_active=bool(state and state.cooldown_until and state.cooldown_until > now),
        near_games=near,
    )
    for name in ("discovery", "daily", "weekly"):
        if jobs[name]["missing"]:
            result["issues"].append({"code": name + "_missing", "job": name})
        elif jobs[name]["overdue"]:
            result["issues"].append({"code": name + "_overdue", "job": name})
    for name in ("live", "final"):
        if jobs[name]["overdue_count"]:
            result["issues"].append(
                {"code": name + "_overdue", "job": name, "count": jobs[name]["overdue_count"]}
            )
    later_success = LoaderRun.objects.filter(
        command=OuterRef("command"),
        scope=OuterRef("scope"),
        status=LoaderRun.Status.SUCCEEDED,
        started_at__gt=OuterRef("started_at"),
    )
    failures = (
        LoaderRun.objects.filter(
            status__in=[LoaderRun.Status.FAILED, LoaderRun.Status.INTERRUPTED],
        )
        .filter(
            Q(finished_at__gte=now - timedelta(hours=lookback_hours))
            | Q(finished_at__isnull=True, started_at__gte=now - timedelta(hours=lookback_hours))
        )
        .annotate(recovered=Exists(later_success))
    )
    unresolved = failures.filter(recovered=False).count()
    running = LoaderRun.objects.filter(status=LoaderRun.Status.RUNNING)
    long_running = running.filter(started_at__lt=now - timedelta(seconds=max_run_seconds))
    result.update(
        unresolved_failure_count=unresolved,
        recent_failures=list(
            failures.order_by("recovered", "-started_at").values(
                "id",
                "command",
                "scope",
                "status",
                "started_at",
                "finished_at",
                "error",
                "recovered",
            )[:limit]
        ),
        running_count=running.count(),
        long_running_count=long_running.count(),
        running=list(
            running.order_by("started_at").values(
                "id", "command", "scope", "started_at", "updated_at", "progress"
            )[:limit]
        ),
    )
    if unresolved:
        result["issues"].append({"code": "unresolved_failures", "count": unresolved})
    if result["long_running_count"]:
        result["issues"].append({"code": "long_running", "count": result["long_running_count"]})
    if result["issues"]:
        result["status"] = "unhealthy"
    return result
