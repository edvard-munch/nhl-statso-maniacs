"""Real PostgreSQL coordination, durable outcomes and command-level integration."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
import os
from pathlib import Path
import select
import subprocess
import sys
from threading import Event

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections, transaction
from django.utils import timezone
import pytest

from players import loader_runs, tasks
from players.loader_runs import LoaderBusy, loader_execution, report_progress
from players.management.commands import upd_tms
from players.models import LoaderRun, Team

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


def events(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def invoke(name="upd_tms", *args, **kwargs):
    return call_command(name, *args, stdout=StringIO(), stderr=StringIO(), **kwargs)


@pytest.mark.parametrize(
    "name,args",
    [
        ("upd_tms", []),
        ("upd_pls", []),
        ("upd_pls_tot", ["--mode", "current"]),
        ("upd_pls_tot", ["--mode", "full"]),
        ("upd_gms", ["--date", "2026-11-08"]),
        ("audit_game_toi", ["--repair", "--json"]),
    ],
)
def test_conflicting_commands_fail_before_network_and_app_writes(
    monkeypatch, requests_mock, name, args
):
    entered, release = Event(), Event()

    def body(self, *args, **options):
        Team.objects.create(nhl_id=1, name="First run")
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(upd_tms.Command, "handle", body)

    def first():
        try:
            invoke()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(first)
        try:
            assert entered.wait(5)
            running = LoaderRun.objects.get(status=LoaderRun.Status.RUNNING)
            with pytest.raises(LoaderBusy, match="Another loader"):
                invoke(name, *args)
            skipped = LoaderRun.objects.get(status=LoaderRun.Status.SKIPPED)
            assert skipped.command == name
            assert skipped.finished_at is not None
            assert skipped.duration_seconds == 0
            assert LoaderRun.objects.get(pk=running.pk).status == LoaderRun.Status.RUNNING
            assert Team.objects.count() == 1
            assert not requests_mock.called
            # Status reads do not compete for the loader lock.
            output = StringIO()
            call_command("loader_status", "--json", stdout=output)
            assert {row["status"] for row in json.loads(output.getvalue())} == {
                "running",
                "skipped",
            }
        finally:
            release.set()
        future.result(timeout=10)
    assert LoaderRun.objects.filter(status=LoaderRun.Status.SUCCEEDED).count() == 1


def test_success_logs_utc_scope_and_throttled_progress(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(loader_runs, "monotonic", lambda: clock[0])
    stream = StringIO()
    with loader_execution("fixture", {"mode": "current"}, stream) as reporter:
        report_progress("players", 0, 3)
        clock[0] += 1
        report_progress("players", 1, 3, item=42)
        assert reporter.run.progress["remaining"] == 2
        assert len(events(stream)) == 2  # start and initial phase only
        clock[0] += loader_runs.PROGRESS_INTERVAL_SECONDS
        report_progress("players", 2, 3, item=43)
        report_progress("players", 3, 3, item=44)
    run = LoaderRun.objects.get()
    assert run.status == LoaderRun.Status.SUCCEEDED
    assert run.scope == {"mode": "current"}
    assert run.progress == {
        "phase": "players",
        "processed": 3,
        "total": 3,
        "remaining": 0,
        "deferred": 0,
        "item": 44,
    }
    assert run.finished_at >= run.started_at
    assert run.duration_seconds == 16
    emitted = events(stream)
    assert [event["event"] for event in emitted] == [
        "started",
        "progress",
        "progress",
        "progress",
        "finished",
    ]
    assert all(event["timestamp"].endswith("+00:00") for event in emitted)
    assert all(event["run_id"] == str(run.pk) for event in emitted)


@pytest.mark.parametrize(
    "failure,status",
    [(RuntimeError, "failed"), (CommandError, "failed"), (KeyboardInterrupt, "interrupted")],
)
def test_failure_releases_lock_and_preserves_outcome_and_prior_commits(
    monkeypatch, failure, status
):
    def body(self, *args, **options):
        Team.objects.create(nhl_id=1, name="Committed before failure")
        report_progress("fixture", 1, 2)
        raise failure("fixture failure")

    monkeypatch.setattr(upd_tms.Command, "handle", body)
    with pytest.raises(failure, match="fixture failure"):
        invoke()
    run = LoaderRun.objects.get()
    assert run.status == status
    assert run.finished_at is not None
    assert run.progress["processed"] == 1
    assert "fixture failure" in run.error
    assert Team.objects.count() == 1  # tracking does not wrap the whole loader
    monkeypatch.setattr(upd_tms.Command, "handle", lambda *args, **options: None)
    invoke()
    assert LoaderRun.objects.filter(status="succeeded").count() == 1


def test_changed_database_session_cannot_continue_writing():
    with pytest.raises(CommandError, match="session changed"):
        with loader_execution("fixture", {}, StringIO()):
            connection.close()
            Team.objects.create(nhl_id=1, name="Must not be published")
    assert Team.objects.count() == 0
    assert LoaderRun.objects.get().status == LoaderRun.Status.FAILED
    with loader_execution("next", {}, StringIO()):
        pass
    assert LoaderRun.objects.filter(status="succeeded").exists()


def test_nested_command_cannot_reenter_its_own_lock(monkeypatch):
    body = []
    monkeypatch.setattr(upd_tms.Command, "handle", lambda *args, **options: body.append(True))
    with loader_execution("outer", {}, StringIO()):
        with pytest.raises(LoaderBusy):
            invoke()
    assert not body
    assert set(LoaderRun.objects.values_list("status", flat=True)) == {"succeeded", "skipped"}


def test_command_in_caller_transaction_is_rejected_before_work(monkeypatch):
    body = []
    monkeypatch.setattr(upd_tms.Command, "handle", lambda *args, **options: body.append(True))
    with transaction.atomic():
        with pytest.raises(CommandError, match="outside an enclosing"):
            invoke()
    assert not body
    assert LoaderRun.objects.count() == 0


def test_missing_migration_gives_actionable_error():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(LoaderRun._meta, "db_table", "missing_fixture_loader_table")
        with pytest.raises(CommandError, match="migrate first"):
            invoke()
    assert LoaderRun.objects.count() == 0


def test_readonly_audit_has_no_loader_run():
    output = StringIO()
    call_command(
        "audit_game_toi", "--season", "20262027", "--json", stdout=output, stderr=StringIO()
    )
    assert json.loads(output.getvalue())["summary"]["games"] == 0
    assert LoaderRun.objects.count() == 0


def test_scope_logging_preserves_stdout_and_ignores_unrelated_options(monkeypatch):
    monkeypatch.setattr(
        upd_tms.Command, "handle", lambda self, *args, **options: self.stdout.write("payload")
    )
    output, status = StringIO(), StringIO()
    call_command("upd_tms", stdout=output, stderr=status, verbosity=0)
    assert output.getvalue() == "payload\n"
    assert status.getvalue() == ""
    assert LoaderRun.objects.get().scope == {}


def test_celery_uses_command_guard_and_records_failure(monkeypatch):
    def body(self, *args, **options):
        raise CommandError("fixture task failure")

    monkeypatch.setattr(upd_tms.Command, "handle", body)
    with pytest.raises(CommandError, match="fixture task failure"):
        tasks.upd_database.apply(throw=True)
    assert LoaderRun.objects.get().command == "upd_tms"
    assert LoaderRun.objects.get().status == LoaderRun.Status.FAILED


def test_hard_process_exit_releases_lock_and_next_run_recovers_status(monkeypatch):
    # Child uses this synthetic pytest database, never the application's DB name.
    env = dict(os.environ, DJANGO_SETTINGS_MODULE="nhl_web_app.hook_test_settings")
    for name, setting in (
        ("NAME", "NAME"),
        ("USER", "USER"),
        ("PASSWORD", "PASSWORD"),
        ("HOST", "HOST"),
        ("PORT", "PORT"),
    ):
        env["NHL_TEST_DB_" + name] = str(connection.settings_dict[setting])
    code = """
import sys
import django
django.setup()
from players.loader_runs import loader_execution
from players.models import Team
with loader_execution("crash_fixture", {}, sys.stderr):
    Team.objects.create(nhl_id=1, name="Committed before process exit")
    print("ready", flush=True)
    sys.stdin.read(1)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0], "Child did not acquire the lock"
        assert process.stdout.readline().strip() == "ready"
        old = LoaderRun.objects.get(command="crash_fixture")
        assert old.status == LoaderRun.Status.RUNNING
        process.terminate()
        process.wait(timeout=5)
        monkeypatch.setattr(upd_tms.Command, "handle", lambda *args, **options: None)
        invoke()
        old.refresh_from_db()
        assert old.status == LoaderRun.Status.INTERRUPTED
        assert "earlier writes may be committed" in old.error
        assert Team.objects.count() == 1
        assert LoaderRun.objects.filter(status="succeeded").exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


@pytest.mark.parametrize("limit", [0, 1001])
def test_status_limit_validation(limit):
    with pytest.raises(CommandError, match="--limit"):
        invoke("loader_status", "--limit", str(limit))


def test_status_lookup_and_empty_output():
    output = StringIO()
    call_command("loader_status", stdout=output)
    assert "No loader runs" in output.getvalue()
    run = LoaderRun.objects.create(
        command="fixture",
        scope={"mode": "current"},
        status="succeeded",
        updated_at=timezone.now(),
        finished_at=timezone.now(),
    )
    output = StringIO()
    call_command("loader_status", "--run-id", str(run.pk), "--json", stdout=output)
    data = json.loads(output.getvalue())
    assert len(data) == 1 and data[0]["id"] == str(run.pk)
    with pytest.raises(CommandError, match="not found"):
        invoke("loader_status", "--run-id", "00000000-0000-0000-0000-000000000000")
