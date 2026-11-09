"""Read-only scheduler health, deadlines and monitoring exit contracts."""

from datetime import datetime, timedelta, timezone as utc
from io import StringIO
import json
import subprocess
import sys

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
import pytest

from players import loader_runs, scheduler_health as health
from players.models import Game, LoaderRun, LoaderScheduleState, ScheduledGame

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
NOW = datetime(2026, 11, 10, 13, tzinfo=utc.utc)  # Tuesday, after Monday's weekly window.


@pytest.fixture
def configured(settings, monkeypatch, requests_mock):
    settings.NHL_SCHEDULING = {**settings.NHL_SCHEDULING, "enabled": True}
    monkeypatch.setattr(health.scheduler.timezone, "now", lambda: NOW)
    return requests_mock


@pytest.fixture
def healthy(configured):
    return LoaderScheduleState.objects.create(
        key=loader_runs.SCHEDULE_STATE_KEY,
        discovered_at=NOW,
        daily_completed_date=NOW.date(),
        weekly_completed_date=NOW.date() - timedelta(days=1),
    )


def run(command="upd_gms", status="failed", age=10, scope=None):
    when = NOW - timedelta(seconds=age)
    return LoaderRun.objects.create(
        command=command,
        status=status,
        scope=scope or {},
        started_at=when,
        updated_at=when,
        finished_at=None if status == "running" else when,
        error="fixture failure" if status == "failed" else "",
    )


def game(**kwargs):
    defaults = dict(
        game_id=2026020001,
        schedule_date=NOW.date(),
        starts_at=NOW - timedelta(hours=1),
        game_state="LIVE",
        schedule_state="OK",
        discovered_at=NOW,
    )
    defaults.update(kwargs)
    return ScheduledGame.objects.create(**defaults)


def snapshot():
    return {
        model: list(model.objects.order_by("pk").values())
        for model in (LoaderScheduleState, ScheduledGame, LoaderRun, Game)
    }


def invoke(**options):
    output, errors = StringIO(), StringIO()
    code = 0
    try:
        call_command("scheduler_health", json_output=True, stdout=output, stderr=errors, **options)
    except CommandError as error:
        code = error.returncode
    return code, json.loads(output.getvalue())


def test_healthy_json_is_read_only_and_contains_no_broker_credentials(
    healthy, configured, settings
):
    settings.CELERY_BROKER_URL = "amqp://secret:password@rabbit.invalid/private"
    before = snapshot()
    code, data = invoke()
    assert code == 0 and data["status"] == "healthy"
    assert data["schema_version"] == 1
    assert not data["services_checked"]
    assert data["jobs"]["discovery"]["last_success"].startswith("2026-11-10")
    assert "password" not in json.dumps(data) and "rabbit.invalid" not in json.dumps(data)
    assert snapshot() == before and not configured.called


def test_enabled_missing_state_is_unhealthy_without_creating_it(configured):
    before = snapshot()
    code, data = invoke()
    assert code == 1
    assert {row["code"] for row in data["issues"]} == {
        "discovery_missing",
        "daily_missing",
        "weekly_missing",
    }
    assert snapshot() == before


@pytest.mark.parametrize("near", [False, True])
def test_discovery_cadence_and_grace_boundary(healthy, near, settings):
    if near:
        game()
    interval = settings.NHL_SCHEDULING["discovery_seconds" if near else "quiet_discovery_seconds"]
    healthy.discovered_at = NOW - timedelta(seconds=interval + 900)
    healthy.save()
    assert not health.report(NOW)["jobs"]["discovery"]["overdue"]
    assert health.report(NOW + timedelta(microseconds=1))["jobs"]["discovery"]["overdue"]
    assert health.report(NOW)["jobs"]["discovery"]["due"]


def test_daily_due_in_quiet_window_becomes_overdue_only_after_deadline(healthy):
    healthy.daily_completed_date = NOW.date() - timedelta(days=1)
    healthy.save()
    in_window = NOW.replace(hour=10)
    row = health.report(in_window)["jobs"]["daily"]
    assert row["due"] and row["eligible_now"] and not row["overdue"]
    deadline = NOW.replace(hour=12, minute=15)
    assert not health.report(deadline)["jobs"]["daily"]["overdue"]
    assert health.report(deadline + timedelta(microseconds=1))["jobs"]["daily"]["overdue"]


def test_weekly_configured_weekday_is_not_overdue_before_its_window(healthy, settings):
    settings.NHL_SCHEDULING = {**settings.NHL_SCHEDULING, "weekly_weekday": 2}
    healthy.weekly_completed_date = NOW.date() - timedelta(days=8)
    healthy.save()
    assert not health.report(NOW)["jobs"]["weekly"]["overdue"]
    wednesday = NOW + timedelta(days=1)
    assert health.report(wednesday)["jobs"]["weekly"]["overdue"]


def test_cross_midnight_sunday_window_does_not_raise_weekly_false_alarm(healthy, settings):
    settings.NHL_SCHEDULING = {
        **settings.NHL_SCHEDULING,
        "quiet_start_hour": 23,
        "quiet_hours": 3,
        "weekly_weekday": 6,
    }
    monday = NOW.replace(day=9, hour=1)
    healthy.daily_completed_date = monday.date() - timedelta(days=2)
    healthy.weekly_completed_date = monday.date() - timedelta(days=8)
    healthy.save()
    rows = health.report(monday)["jobs"]
    assert rows["daily"]["due"] and not rows["daily"]["overdue"]
    assert not rows["weekly"]["overdue"]
    after = monday.replace(hour=3)
    assert health.report(after)["jobs"]["weekly"]["overdue"]
    assert health.report(after)["jobs"]["daily"]["overdue"]


def test_active_games_block_maintenance_but_do_not_hide_missed_deadlines(healthy):
    game()
    healthy.daily_completed_date = NOW.date() - timedelta(days=1)
    healthy.save()
    row = health.report(NOW)["jobs"]["daily"]
    assert row["overdue"] and not row["eligible_now"]
    assert row["blocked_by"] == "active_or_imminent_games"


def test_attempts_are_not_success_and_display_limit_does_not_hide_overdue_games(healthy):
    first = game(last_live_attempt_at=NOW)
    game(game_id=2026020002)
    first_saved = Game.objects.create(nhl_id=first.game_id, slug="healthy-game", result="fixture")
    Game.objects.filter(pk=first_saved.pk).update(updated_date=NOW)
    data = health.report(NOW, limit=1)
    row = data["jobs"]["live"]
    assert row["eligible_count"] == 2 and row["overdue_count"] == 1
    assert row["games"][0]["game_id"] == 2026020002
    assert row["truncated"]
    # A recent attempt without a saved game does not clear the missing-publication warning.
    ScheduledGame.objects.filter(pk=2026020002).update(last_live_attempt_at=NOW)
    row = health.report(NOW)["jobs"]["live"]
    assert row["due_count"] == 0 and row["overdue_count"] == 1


def test_final_gets_its_own_deadline_and_expired_or_postponed_rows_are_not_selected(healthy):
    game(game_state="OFF", first_final_seen_at=NOW)
    game(game_id=2026020002, game_state="OFF", first_final_seen_at=NOW - timedelta(hours=2))
    game(game_id=2026020003, schedule_state="PPD")
    game(game_id=2026020004, discovered_at=NOW - timedelta(days=1))
    rows = health.report(NOW)["jobs"]
    assert rows["final"]["eligible_count"] == 1 and rows["final"]["overdue_count"] == 0
    assert rows["live"]["eligible_count"] == 0
    later = NOW + timedelta(minutes=26)
    # Keep the discovery snapshot eligible while testing the final's publication deadline.
    ScheduledGame.objects.filter(pk=2026020001).update(discovered_at=later)
    assert health.report(later)["jobs"]["final"]["overdue_count"] == 1


def test_cooldown_is_reported_but_not_unhealthy_by_itself(healthy):
    healthy.cooldown_until = NOW + timedelta(minutes=5)
    healthy.save()
    data = health.report(NOW)
    assert data["cooldown_active"] and data["status"] == "healthy"


def test_failures_require_later_success_for_exact_command_and_scope(healthy):
    scope = {"game_ids": ["2026020001"], "state": "started"}
    failed = run(scope=scope, age=30)
    run(status="succeeded", age=20, scope={"game_ids": ["2026020002"]})
    assert health.report(NOW)["unresolved_failure_count"] == 1
    run(status="succeeded", age=10, scope=scope)
    data = health.report(NOW)
    assert data["status"] == "healthy" and data["recent_failures"][0]["recovered"]
    assert LoaderRun.objects.get(pk=failed.pk).status == "failed"


def test_failure_counts_ignore_display_limit_and_respect_lookback(healthy):
    for index in range(3):
        run(scope={"game_ids": [str(index)]})
    run(age=25 * 3600)
    run(status="skipped")
    data = health.report(NOW, limit=1)
    assert data["unresolved_failure_count"] == 3 and len(data["recent_failures"]) == 1


def test_long_running_reports_age_without_mutating_or_claiming_interruption(healthy):
    active = run(status="running", age=3601)
    before = snapshot()
    data = health.report(NOW)
    assert data["long_running_count"] == 1 and data["status"] == "unhealthy"
    assert data["running"][0]["id"] == active.id
    assert snapshot() == before
    assert not health.report(NOW, max_run_seconds=7200)["long_running_count"]


def test_database_error_is_unknown_and_json_stays_parseable(configured, monkeypatch):
    def unavailable(*args, **kwargs):
        raise DatabaseError("must not expose connection details")

    monkeypatch.setattr(health, "report", unavailable)
    code, data = invoke()
    assert code == 3 and data["status"] == "unknown"
    assert "connection details" not in json.dumps(data)


def test_human_output_includes_issues_and_last_success(healthy):
    run()
    output = StringIO()
    with pytest.raises(CommandError) as error:
        call_command("scheduler_health", stdout=output)
    assert error.value.returncode == 1
    assert "UNHEALTHY" in output.getvalue() and "last_success" in output.getvalue()
    assert "unresolved_failures" in output.getvalue()


@pytest.mark.parametrize(
    "name,value",
    [("limit", 0), ("grace_seconds", -1), ("max_run_seconds", 0), ("failure_lookback_hours", 0)],
)
def test_invalid_thresholds_fail_before_queries(configured, name, value, django_assert_num_queries):
    with django_assert_num_queries(0), pytest.raises(CommandError) as error:
        call_command("scheduler_health", **{name: value})
    assert error.value.returncode == 3


def test_disabled_needs_no_database(settings, django_assert_num_queries):
    settings.NHL_SCHEDULING = {**settings.NHL_SCHEDULING, "enabled": False}
    with django_assert_num_queries(0):
        code, data = invoke()
    assert code == 2 and data["status"] == "disabled"
    assert "jobs" not in data


def test_real_cli_emits_json_stdout_and_disabled_exit_code(configured):
    import os

    result = subprocess.run(
        [sys.executable, "manage.py", "scheduler_health", "--json"],
        env={**os.environ, "NHL_SCHEDULING_ENABLED": "False"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "disabled"


def test_command_uses_only_selects_and_never_acquires_locks(healthy):
    from django.db import connection

    def read_only(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith("SELECT")
        assert "advisory" not in sql.lower() and "for update" not in sql.lower()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(read_only):
        assert invoke()[0] == 0


def test_recent_completion_of_long_failed_run_is_not_hidden_by_old_start(healthy):
    failed = run(age=48 * 3600)
    failed.finished_at = NOW
    failed.save(update_fields=["finished_at"])
    assert health.report(NOW)["unresolved_failure_count"] == 1


def test_cli_database_unavailable_has_unknown_exit_and_json(configured, tmp_path):
    import os

    result = subprocess.run(
        [sys.executable, "manage.py", "scheduler_health", "--json"],
        env={
            **os.environ,
            "NHL_SCHEDULING_ENABLED": "True",
            "CELERY_BROKER_URL": "amqp://fixture:unused@rabbit.invalid/nhl",
            "NHL_TEST_DB_HOST": str(tmp_path / "nonexistent-socket"),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["status"] == "unknown"
