"""Schedule-aware Celery work selection; all NHL writes use the command guard."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as datetime_timezone
import json
import logging
import sys
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import management
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
import requests

from . import loader_runs
from .loader_runs import (
    LoaderBusy,
    LoaderCooldown,
    LoaderSessionLost,
    loader_execution,
    report_progress,
)
from .management.commands import upd_gms as games
from .models import LoaderRun, LoaderScheduleState, ScheduledGame

logger = logging.getLogger(__name__)
SLOTS = {"discovery": 2, "live": 3, "final": 4, "maintenance": 5, "cleanup": 6}
MAX_ACTIVE_AGE = timedelta(days=1)
SOFT_FINAL_STATES = games.ACTIVE_GAME_STATES | {games.GAME_STATES["softFinal"]}


def control():
    return LoaderScheduleState.objects.get_or_create(key=loader_runs.SCHEDULE_STATE_KEY)[0]


def outcome(status, **details):
    result = {"status": status, **details}
    logger.info(json.dumps({"timestamp": timezone.now().isoformat(), **result}, default=str))
    return result


@contextmanager
def task_slot(name):
    if connection.in_atomic_block:
        raise CommandError("Scheduled loader tasks require committed transactions")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s, %s)", [loader_runs.LOCK_NAMESPACE, SLOTS[name]]
        )
        acquired = cursor.fetchone()[0]
    held = connection.connection

    def same_session(execute, sql, params, many, context):
        if connection.connection is not held or held.closed:
            raise LoaderSessionLost("Scheduled task lost its coalescing lock")
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(same_session):
            yield acquired
    finally:
        if acquired and connection.connection is held and not held.closed:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s, %s)", [loader_runs.LOCK_NAMESPACE, SLOTS[name]]
                )


def run(name, function):
    if not settings.NHL_SCHEDULING["enabled"]:
        return outcome("disabled", job=name)
    with task_slot(name) as acquired:
        if not acquired:
            return outcome("deferred", job=name, reason="same job already running")
        try:
            return function()
        except (LoaderBusy, LoaderCooldown) as error:
            return outcome("deferred", job=name, reason=str(error))


def near_games(now):
    return (
        ScheduledGame.objects.filter(
            schedule_state=games.SCHEDULE_OK, starts_at__gte=now - MAX_ACTIVE_AGE
        )
        .filter(
            Q(game_state__in=SOFT_FINAL_STATES)
            | Q(
                game_state__in=games.PREGAME_STATES,
                starts_at__lte=now + timedelta(seconds=settings.NHL_SCHEDULING["pre_game_seconds"]),
            )
        )
        .exists()
    )


def snapshot_due(now):
    last = control().discovered_at
    interval = settings.NHL_SCHEDULING[
        "discovery_seconds" if near_games(now) else "quiet_discovery_seconds"
    ]
    return last is None or last <= now - timedelta(seconds=interval)


def discover(force=False):
    now = timezone.now()
    if not force and not snapshot_due(now):
        return outcome("not_due", job="discovery")
    # One week from yesterday includes games straddling Pacific midnight and
    # upcoming starts without fetching future-game boxscores.
    day = now.astimezone(ZoneInfo(games.TIMEZONE)).date() - timedelta(days=1)
    with loader_execution("discover_games", {"date": day.isoformat()}, sys.stderr):
        with requests.Session() as session:
            payload = games.fetch_json(
                games.URL_SCHEDULE.format(day), "scheduled discovery", session, {"gameWeek"}
            )
        staged, seen = [], set()
        week = payload["gameWeek"]
        if not isinstance(week, list) or not week:
            raise CommandError("Discovery requires a nonempty gameWeek")
        dates = set()
        for weekday in week:
            if not isinstance(weekday, dict) or not isinstance(weekday.get("games"), list):
                raise CommandError("Invalid discovered schedule day")
            date = games.parse_target_date(weekday.get("date"))
            if date in dates:
                raise CommandError("Duplicate discovered schedule date")
            dates.add(date)
            for game in weekday["games"]:
                if not isinstance(game, dict) or type(game.get("id")) is not int:
                    raise CommandError("Invalid discovered game identity")
                if not games.regular_season_game(game):
                    continue
                game_id = games.parse_target_game_id(game["id"])
                if game_id in seen:
                    raise CommandError("Duplicate discovered game ID")
                seen.add(game_id)
                state = games.target_state(game)
                try:
                    starts = datetime.fromisoformat(game["startTimeUTC"])
                except (KeyError, ValueError, TypeError) as error:
                    raise CommandError(f"Game {game_id} requires an aware startTimeUTC") from error
                if not timezone.is_aware(starts) or not isinstance(
                    game.get("gameScheduleState"), str
                ):
                    raise CommandError(f"Game {game_id} requires an aware start and schedule state")
                staged.append(
                    (
                        game_id,
                        date,
                        starts.astimezone(datetime_timezone.utc),
                        state,
                        game["gameScheduleState"],
                    )
                )
        if day not in dates:
            raise CommandError("Discovery response does not cover requested date")
        report_progress("schedule_publication", total=len(staged))
        with transaction.atomic():
            for index, (game_id, date, starts, state, schedule_state) in enumerate(staged, start=1):
                saved = ScheduledGame.objects.filter(pk=game_id).first()
                first_final = (
                    ((saved.first_final_seen_at if saved else None) or now)
                    if state in games.FINAL_GAME_STATES
                    else None
                )
                defaults = {
                    "schedule_date": date,
                    "starts_at": starts,
                    "game_state": state,
                    "schedule_state": schedule_state,
                    "discovered_at": now,
                    "first_final_seen_at": first_final,
                }
                if state not in games.FINAL_GAME_STATES:
                    defaults["last_final_attempt_at"] = None
                ScheduledGame.objects.update_or_create(game_id=game_id, defaults=defaults)
                report_progress("schedule_publication", index, len(staged), item=game_id)
            LoaderScheduleState.objects.filter(pk=loader_runs.SCHEDULE_STATE_KEY).update(
                discovered_at=now
            )
    return outcome("succeeded", job="discovery", games=len(staged))


def ensure_snapshot():
    if snapshot_due(timezone.now()):
        discover(force=True)


def refresh_group(final=False):
    ensure_snapshot()
    now = timezone.now()
    options = settings.NHL_SCHEDULING
    selected = ScheduledGame.objects.filter(
        schedule_state=games.SCHEDULE_OK,
        discovered_at__gte=now
        - timedelta(seconds=options["quiet_discovery_seconds"] + options["discovery_seconds"]),
    )
    if final:
        interval = options["final_seconds"]
        selected = selected.filter(
            game_state__in=games.FINAL_GAME_STATES,
            first_final_seen_at__gte=now - timedelta(seconds=options["final_window_seconds"]),
        )
        attempt_field = "last_final_attempt_at"
    else:
        interval = options["live_seconds"]
        selected = selected.filter(
            game_state__in=SOFT_FINAL_STATES, starts_at__gte=now - MAX_ACTIVE_AGE
        )
        attempt_field = "last_live_attempt_at"
    selected = selected.filter(
        Q(**{attempt_field + "__isnull": True})
        | Q(**{attempt_field + "__lte": now - timedelta(seconds=interval)})
    )
    failures, processed = [], 0
    for game_id in selected.order_by("starts_at", "game_id").values_list("game_id", flat=True):
        try:
            management.call_command(
                "upd_gms", game_ids=[str(game_id)], state="final" if final else games.TARGET_STARTED
            )
        except (LoaderBusy, LoaderCooldown, LoaderSessionLost):
            raise
        except CommandError:
            failures.append(game_id)
        ScheduledGame.objects.filter(pk=game_id).update(**{attempt_field: now})
        processed += 1
    if failures:
        raise CommandError(f"Scheduled game refresh failed for {failures}; see loader_status")
    return outcome("succeeded", job="final" if final else "live", processed=processed)


def maintenance_date():
    now = timezone.now().astimezone(datetime_timezone.utc)
    options = settings.NHL_SCHEDULING
    if (now.hour - options["quiet_start_hour"]) % 24 >= options["quiet_hours"]:
        return None
    if near_games(now):
        return None
    return now.date() - timedelta(days=int(now.hour < options["quiet_start_hour"]))


def weekly_due(day):
    last = control().weekly_completed_date
    week = day - timedelta(days=day.weekday())
    return last is None or (
        day.weekday() >= settings.NHL_SCHEDULING["weekly_weekday"] and last < week
    )


def update_teams(day):
    if weekly_due(day):
        management.call_command("upd_tms")
        LoaderScheduleState.objects.filter(pk=loader_runs.SCHEDULE_STATE_KEY).update(
            weekly_completed_date=day
        )


def maintenance(teams_only=False):
    ensure_snapshot()
    day = maintenance_date()
    if day is None:
        return outcome(
            "deferred", job="maintenance", reason="outside quiet window or games active/imminent"
        )
    if teams_only:
        update_teams(day)
        return outcome("succeeded", job="weekly")
    if control().daily_completed_date and control().daily_completed_date >= day:
        return outcome("not_due", job="daily")
    update_teams(day)  # also bootstraps missing team metadata on the first run
    for command, kwargs in (("upd_pls", {}), ("upd_pls_tot", {"mode": "current"})):
        if maintenance_date() != day:
            return outcome("deferred", job="daily", reason="quiet window ended")
        management.call_command(command, **kwargs)
    today = timezone.now().astimezone(ZoneInfo(games.TIMEZONE)).date()
    recent = [
        (today - timedelta(days=index)).isoformat()
        for index in range(1, settings.NHL_SCHEDULING["recent_days"] + 1)
    ]
    if maintenance_date() != day:
        return outcome("deferred", job="daily", reason="quiet window ended")
    management.call_command("upd_gms", dates=recent, state="final")
    LoaderScheduleState.objects.filter(pk=loader_runs.SCHEDULE_STATE_KEY).update(
        daily_completed_date=day
    )
    return outcome("succeeded", job="daily", date=day.isoformat())


def cleanup():
    cutoff = timezone.now() - timedelta(days=settings.NHL_SCHEDULING["run_retention_days"])
    count, _ = (
        LoaderRun.objects.exclude(status=LoaderRun.Status.RUNNING)
        .filter(finished_at__lt=cutoff)
        .delete()
    )
    return outcome("succeeded", job="cleanup", deleted=count)
