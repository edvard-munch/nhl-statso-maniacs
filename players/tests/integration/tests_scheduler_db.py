"""Opt-in Beat configuration and persistent schedule-aware task execution."""

from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import Mock, call

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import CommandError
from django.db import connections
from django.test import override_settings
import pytest

from nhl_web_app.celery_schedule import beat_schedule, read_options, TASK_ROUTES, INTERVAL_DEFAULTS
from players import scheduler, tasks, loader_runs
from players.loader_runs import LoaderBusy, LoaderCooldown, loader_execution
from players.management.commands import upd_gms
from players.models import LoaderRun, LoaderScheduleState, ScheduledGame

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 11, 9, 10, tzinfo=dt_timezone.utc)


@pytest.fixture
def options():
    defaults = read_options(lambda key, cast=str, default=None: default)
    return {**defaults, "enabled": True}


@pytest.fixture
def scheduled(options, monkeypatch):
    monkeypatch.setattr(scheduler.timezone, "now", lambda: NOW)
    with override_settings(NHL_SCHEDULING=options):
        yield


@pytest.fixture
def snapshot(scheduled):
    return LoaderScheduleState.objects.create(key=loader_runs.SCHEDULE_STATE_KEY, discovered_at=NOW)


def entry(**kwargs):
    values = dict(
        game_id=2026020001,
        schedule_date="2026-11-08",
        starts_at=NOW - timedelta(hours=3),
        game_state="LIVE",
        schedule_state="OK",
        discovered_at=NOW,
    )
    values.update(kwargs)
    return ScheduledGame.objects.create(**values)


def register_schedule(requests_mock, rows=None):
    rows = (
        rows
        if rows is not None
        else [
            {
                "id": 2026020001,
                "gameState": "OFF",
                "gameScheduleState": "OK",
                "startTimeUTC": "2026-11-09T01:00:00Z",
            }
        ]
    )
    requests_mock.get(
        upd_gms.URL_SCHEDULE.format("2026-11-08"),
        json={"gameWeek": [{"date": "2026-11-08", "games": rows}]},
    )
    return rows


def test_disabled_tasks_do_not_touch_database_or_network(requests_mock):
    with override_settings(NHL_SCHEDULING={**settings.NHL_SCHEDULING, "enabled": False}):
        for task in (
            tasks.discover_games,
            tasks.refresh_live_games,
            tasks.refresh_final_games,
            tasks.refresh_daily,
            tasks.refresh_teams,
            tasks.cleanup_history,
        ):
            assert task.apply(throw=True).result["status"] == "disabled"
    assert not requests_mock.called
    assert LoaderRun.objects.count() == LoaderScheduleState.objects.count() == 0


def test_beat_entries_expire_route_and_use_correct_named_tasks(options):
    from celery.beat import Scheduler
    from nhl_web_app.celery_settings import app

    schedule = beat_schedule(options, "amqp://test:unused@rabbit.invalid/nhl")
    assert len(schedule) == 7
    names = {item["task"] for item in schedule.values()}
    assert "players.tasks.upd_database" not in names
    assert all(item["options"]["expires"] > 0 for item in schedule.values())
    for item in schedule.values():
        assert item["options"]["queue"] == TASK_ROUTES[item["task"]]["queue"]
    assert schedule["nhl-live"]["schedule"] == 300
    assert schedule["nhl-final"]["schedule"] == 600
    beat = Scheduler(app=app, lazy=True)
    install = Mock()
    beat.update_from_dict = install
    beat.install_default_entries(schedule)
    assert install.call_args == call({})  # no second, unrouted cleanup entry
    assert beat_schedule({**options, "enabled": False}, "") == {}
    assert settings.CELERY_TIMEZONE == "UTC"
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1


@pytest.mark.parametrize("broker", ["", "redis://localhost/0", "amqp:///", "memory://"])
def test_enabled_schedule_requires_supported_explicit_broker(options, broker):
    with pytest.raises(ImproperlyConfigured, match="RabbitMQ"):
        beat_schedule(options, broker)


@pytest.mark.parametrize(
    "name,value",
    [
        ("NHL_LIVE_SECONDS", 0),
        ("NHL_QUIET_START_HOUR", 24),
        ("NHL_QUIET_HOURS", 0),
        ("NHL_RECENT_DAYS", 8),
    ],
)
def test_invalid_scheduling_configuration_is_rejected(name, value):
    def env(key, cast=str, default=None):
        return cast(value) if key == name else default

    with pytest.raises(ImproperlyConfigured, match=name):
        read_options(env)


def test_configuration_defaults_are_disabled_and_bounded():
    options = read_options(lambda key, cast=str, default=None: default)
    assert options["enabled"] is False
    assert all(options[name] == value for name, value in INTERVAL_DEFAULTS.items())


def test_discovery_persists_final_window_and_does_not_extend_it(
    scheduled, requests_mock, monkeypatch
):
    register_schedule(requests_mock)
    assert tasks.discover_games.apply(throw=True).result["games"] == 1
    game = ScheduledGame.objects.get()
    assert game.first_final_seen_at == NOW
    assert game.schedule_date.isoformat() == "2026-11-08"
    later = NOW + timedelta(hours=2)
    monkeypatch.setattr(scheduler.timezone, "now", lambda: later)
    scheduler.discover(force=True)
    game.refresh_from_db()
    assert game.first_final_seen_at == NOW
    assert game.discovered_at == later
    assert LoaderRun.objects.filter(command="discover_games", status="succeeded").count() == 2


@pytest.mark.parametrize("bad", ["duplicate", "naive", "missing_date", "bad_state"])
def test_discovery_validation_preserves_previous_snapshot(scheduled, requests_mock, bad):
    original = entry()
    rows = register_schedule(requests_mock)
    if bad == "duplicate":
        rows *= 2
    elif bad == "naive":
        rows[0]["startTimeUTC"] = "2026-11-08T20:00:00"
    elif bad == "bad_state":
        rows[0]["gameState"] = "bad"
    if bad == "missing_date":
        requests_mock.get(
            upd_gms.URL_SCHEDULE.format("2026-11-08"),
            json={"gameWeek": [{"date": "2026-11-07", "games": rows}]},
        )
    else:
        register_schedule(requests_mock, rows)
    with pytest.raises(CommandError):
        tasks.discover_games.apply(throw=True)
    original.refresh_from_db()
    assert original.game_state == "LIVE"
    assert ScheduledGame.objects.count() == 1
    assert LoaderRun.objects.get().status == "failed"


def test_quiet_discovery_skips_until_due_but_near_start_uses_fast_interval(snapshot, requests_mock):
    snapshot.discovered_at = NOW - timedelta(minutes=10)
    snapshot.save()
    assert tasks.discover_games.apply(throw=True).result["status"] == "not_due"
    assert not requests_mock.called
    entry(game_state="FUT", starts_at=NOW + timedelta(minutes=30))
    register_schedule(requests_mock)
    assert tasks.discover_games.apply(throw=True).result["status"] == "succeeded"


def test_live_selection_includes_soft_final_and_coalesces_repeated_ticks(snapshot, monkeypatch):
    one = entry()
    entry(game_id=2026020002, game_state="OVER")
    entry(game_id=2026020003, game_state="FUT")
    entry(game_id=2026020004, game_state="LIVE", schedule_state="PPD")
    entry(game_id=2026020005, starts_at=NOW - timedelta(days=2))
    command = Mock()
    monkeypatch.setattr(scheduler.management, "call_command", command)
    assert tasks.refresh_live_games.apply(throw=True).result["processed"] == 2
    assert [item.kwargs["game_ids"] for item in command.call_args_list] == [
        ["2026020001"],
        ["2026020002"],
    ]
    assert tasks.refresh_live_games.apply(throw=True).result["processed"] == 0
    one.refresh_from_db()
    assert one.last_live_attempt_at == NOW


def test_final_selection_stops_after_window_and_keeps_pending_for_daily(snapshot, monkeypatch):
    entry(game_state="OFF", first_final_seen_at=NOW - timedelta(minutes=30))
    entry(game_id=2026020002, game_state="OFF", first_final_seen_at=NOW - timedelta(hours=2))
    command = Mock()
    monkeypatch.setattr(scheduler.management, "call_command", command)
    assert tasks.refresh_final_games.apply(throw=True).result["processed"] == 1
    assert command.call_args == call("upd_gms", game_ids=["2026020001"], state="final")
    assert ScheduledGame.objects.count() == 2


def test_one_failed_game_does_not_suppress_other_games(snapshot, monkeypatch):
    entry()
    entry(game_id=2026020002)
    command = Mock(side_effect=[CommandError("bad game"), None])
    monkeypatch.setattr(scheduler.management, "call_command", command)
    with pytest.raises(CommandError, match="2026020001"):
        tasks.refresh_live_games.apply(throw=True)
    assert command.call_count == 2


@pytest.mark.parametrize("error", [LoaderBusy("busy"), LoaderCooldown("cooldown")])
def test_contention_or_cooldown_defers_without_immediate_retry(snapshot, monkeypatch, error):
    entry()
    command = Mock(side_effect=error)
    monkeypatch.setattr(scheduler.management, "call_command", command)
    assert tasks.refresh_live_games.apply(throw=True).result["status"] == "deferred"
    assert command.call_count == 1


def test_daily_bootstrap_order_recent_dates_and_once_per_day(snapshot, monkeypatch):
    command = Mock()
    monkeypatch.setattr(scheduler.management, "call_command", command)
    assert tasks.refresh_daily.apply(throw=True).result["status"] == "succeeded"
    assert command.call_args_list == [
        call("upd_tms"),
        call("upd_pls"),
        call("upd_pls_tot", mode="current"),
        call("upd_gms", dates=["2026-11-08", "2026-11-07", "2026-11-06"], state="final"),
    ]
    assert tasks.refresh_daily.apply(throw=True).result["status"] == "not_due"
    assert command.call_count == 4
    assert tasks.refresh_teams.apply(throw=True).result["status"] == "succeeded"
    assert command.call_count == 4


@pytest.mark.parametrize("reason", ["outside_window", "active", "imminent"])
def test_maintenance_defers_heavy_work(snapshot, monkeypatch, reason):
    if reason == "outside_window":
        monkeypatch.setattr(scheduler.timezone, "now", lambda: NOW.replace(hour=20))
        snapshot.discovered_at = NOW.replace(hour=20)
        snapshot.save()
    elif reason == "active":
        entry()
    else:
        entry(game_state="FUT", starts_at=NOW + timedelta(minutes=30))
    command = Mock()
    monkeypatch.setattr(scheduler.management, "call_command", command)
    assert tasks.refresh_daily.apply(throw=True).result["status"] == "deferred"
    assert not command.called
    snapshot.refresh_from_db()
    assert snapshot.daily_completed_date is None


def test_daily_failure_does_not_mark_complete_or_run_later_stages(snapshot, monkeypatch):
    command = Mock(side_effect=[None, CommandError("players failed")])
    monkeypatch.setattr(scheduler.management, "call_command", command)
    with pytest.raises(CommandError, match="players failed"):
        tasks.refresh_daily.apply(throw=True)
    assert command.call_args_list == [call("upd_tms"), call("upd_pls")]
    snapshot.refresh_from_db()
    assert snapshot.daily_completed_date is None
    assert snapshot.weekly_completed_date == NOW.date()


def test_cleanup_preserves_running_and_recent_runs(snapshot):
    old = NOW - timedelta(days=40)
    LoaderRun.objects.create(command="old", status="succeeded", updated_at=old, finished_at=old)
    LoaderRun.objects.create(command="active", status="running", updated_at=old)
    LoaderRun.objects.create(command="recent", status="failed", updated_at=NOW, finished_at=NOW)
    assert tasks.cleanup_history.apply(throw=True).result["deleted"] == 1
    assert set(LoaderRun.objects.values_list("command", flat=True)) == {"active", "recent"}


def test_exhausted_429_creates_shared_cooldown_and_blocks_manual_and_tasks(
    scheduled, requests_mock
):
    requests_mock.get(
        upd_gms.URL_SCHEDULE.format("2026-11-08"), status_code=429, headers={"Retry-After": "3600"}
    )
    with pytest.raises(CommandError):
        scheduler.discover(force=True)
    state = LoaderScheduleState.objects.get()
    assert state.cooldown_until == NOW + timedelta(hours=1)
    calls = len(requests_mock.request_history)
    with pytest.raises(LoaderCooldown):
        with loader_execution("manual_fixture", {}, StringIO()):
            pytest.fail("cooldown was bypassed")
    assert tasks.discover_games.apply(throw=True).result["status"] == "deferred"
    assert len(requests_mock.request_history) == calls
    assert "next_retry_at" in LoaderRun.objects.get(status="failed").progress


def test_cooldown_expires_and_permanent_errors_do_not_create_it(
    scheduled, requests_mock, monkeypatch
):
    state = scheduler.control()
    state.cooldown_until = NOW - timedelta(seconds=1)
    state.save()
    register_schedule(requests_mock)
    scheduler.discover(force=True)
    requests_mock.get(upd_gms.URL_SCHEDULE.format("2026-11-08"), status_code=404)
    with pytest.raises(CommandError):
        scheduler.discover(force=True)
    state.refresh_from_db()
    assert state.cooldown_until < NOW


def test_job_lock_coalesces_separate_connections(scheduled):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()

    def first():
        try:
            with scheduler.task_slot("live") as acquired:
                assert acquired
                entered.set()
                assert release.wait(10)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(first)
        try:
            assert entered.wait(5)
            result = scheduler.run("live", lambda: pytest.fail("duplicate job ran"))
            assert result["status"] == "deferred"
        finally:
            release.set()
        future.result(timeout=10)


@pytest.mark.parametrize(
    "instant,expected",
    [("2026-03-08T07:30:00+00:00", "2026-03-07"), ("2026-11-01T07:30:00+00:00", "2026-11-01")],
)
def test_recent_dates_use_pacific_schedule_day_across_dst(snapshot, monkeypatch, instant, expected):
    moment = datetime.fromisoformat(instant)
    monkeypatch.setattr(scheduler.timezone, "now", lambda: moment)
    snapshot.discovered_at = moment
    snapshot.save()
    with override_settings(NHL_SCHEDULING={**settings.NHL_SCHEDULING, "quiet_hours": 24}):
        command = Mock()
        monkeypatch.setattr(scheduler.management, "call_command", command)
        scheduler.maintenance()
    assert (
        command.call_args.kwargs["dates"][0]
        == (datetime.fromisoformat(expected).date() - timedelta(days=1)).isoformat()
    )
