"""Logging routing, correlation and retention adapters without a real worker/broker."""

from io import StringIO
import json
import logging
from logging.handlers import WatchedFileHandler
import subprocess
import sys
from unittest.mock import Mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ImproperlyConfigured
import pytest

from nhl_web_app.logging_config import (
    ConsoleEvents,
    JsonFormatter,
    bind_context,
    configuration,
    context_fields,
)
from players import tasks
from players.models import LoaderRun
from players.management.commands import upd_tms

pytestmark = pytest.mark.integration


@pytest.fixture
def collected_logs():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)


def test_existing_loader_loggers_survive_configuration_and_route_once():
    # Real dictConfig in an isolated process; don't alter pytest's capture handlers.
    code = """
import logging, logging.config
from nhl_web_app.logging_config import configuration
http = logging.getLogger('players.nhl_http')
game = logging.getLogger('players.management.commands.upd_gms')
logging.config.dictConfig(configuration('.', 'console'))
http.warning('retry fixture')
game.warning('missing roster fixture')
logging.getLogger('celery.worker').info('worker fixture')
logging.getLogger('django.request').warning('request fixture')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    rows = [json.loads(line) for line in result.stderr.splitlines()]
    assert [row["message"] for row in rows] == [
        "retry fixture",
        "missing roster fixture",
        "worker fixture",
        "request fixture",
    ]
    assert all(row["timestamp"].endswith("+00:00") for row in rows)
    assert not result.stdout


def test_console_mode_does_not_open_log_file_and_invalid_destination_fails(tmp_path):
    config = configuration(tmp_path, "console")
    assert config["handlers"]["application"]["class"] == "logging.StreamHandler"
    assert not (tmp_path / "logs").exists()
    with pytest.raises(ImproperlyConfigured, match="NHL_LOG_DESTINATION"):
        configuration(tmp_path, "invalid")


def test_file_handler_reopens_after_host_rotation(tmp_path):
    path = tmp_path / "fixture.log"
    handler = WatchedFileHandler(path, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    try:
        handler.handle(logging.makeLogRecord({"msg": "before rotation"}))
        path.rename(tmp_path / "fixture.log.1")
        handler.handle(logging.makeLogRecord({"msg": "after rotation"}))
    finally:
        handler.close()
    assert json.loads(path.read_text())["message"] == "after rotation"
    assert json.loads((tmp_path / "fixture.log.1").read_text())["message"] == "before rotation"
    assert configuration(tmp_path)["handlers"]["application"]["class"].endswith(
        "WatchedFileHandler"
    )


@pytest.mark.django_db(transaction=True)
def test_eager_task_correlates_http_loader_and_lifecycle_without_duplicate_stderr(
    monkeypatch, collected_logs
):
    def body(self, *args, **kwargs):
        logging.getLogger("players.nhl_http").warning("retry fixture")

    monkeypatch.setattr(upd_tms.Command, "handle", body)
    stream = StringIO()
    monkeypatch.setattr(
        tasks.management,
        "call_command",
        lambda *a, **kw: call_command("upd_tms", stderr=stream, stdout=StringIO()),
    )
    result = tasks.upd_database.apply(task_id="logging-fixture-task", throw=True)
    rows = [
        row
        for row in collected_logs()
        if row.get("task_id") == "logging-fixture-task" and row["logger"].startswith("players.")
    ]
    assert result.successful()
    assert rows[0]["event"] == "task_started"
    assert rows[-1]["event"] == "task_finished"
    assert rows[-1]["status"] == "succeeded"
    assert all(row["job"] == "legacy" for row in rows)
    assert all(row["task_name"] == "players.tasks.upd_database" for row in rows)
    warnings = [row for row in rows if row.get("message") == "retry fixture"]
    assert len(warnings) == 3
    assert all(row["command"] == "upd_tms" and row["run_id"] for row in warnings)
    assert len({row["run_id"] for row in warnings}) == 3
    assert not stream.getvalue()
    assert context_fields().get("run_id") is None
    assert context_fields().get("job") is None
    assert LoaderRun.objects.filter(status="succeeded").count() == 3


@pytest.mark.django_db(transaction=True)
def test_loader_and_task_failures_have_severity_traceback_and_propagate(
    monkeypatch, collected_logs
):
    def body(self, *args, **kwargs):
        raise CommandError("synthetic failure")

    monkeypatch.setattr(upd_tms.Command, "handle", body)
    with pytest.raises(CommandError, match="synthetic failure"):
        tasks.upd_database.apply(task_id="failed-logging-fixture", throw=True)
    rows = collected_logs()
    failures = [
        row
        for row in rows
        if row.get("event") in ("finished", "task_finished") and row.get("status") == "failed"
    ]
    assert len(failures) == 2
    assert all(row["level"] == "ERROR" and "CommandError" in row["traceback"] for row in failures)
    assert all(row["task_id"] == "failed-logging-fixture" for row in failures)
    assert LoaderRun.objects.get().status == "failed"
    assert context_fields().get("job") is None


def test_context_is_restored_after_nested_exception():
    with bind_context(job="outer"):
        with pytest.raises(RuntimeError):
            with bind_context(run_id="inner", job="inner"):
                raise RuntimeError("fixture")
        assert context_fields()["job"] == "outer"
        assert "run_id" not in context_fields()
    assert "job" not in context_fields()


def test_console_filter_keeps_task_events_but_not_direct_command_duplicates():
    record = logging.makeLogRecord({"console_event": True})
    assert not ConsoleEvents().filter(record)
    assert ConsoleEvents().filter(logging.makeLogRecord({"msg": "normal warning"}))


def test_worker_logging_signal_uses_django_configuration(monkeypatch, settings):
    from nhl_web_app.celery_settings import configure_worker_logging

    configure = Mock()
    monkeypatch.setattr("logging.config.dictConfig", configure)
    configure_worker_logging()
    configure.assert_called_once_with(settings.LOGGING)


@pytest.mark.parametrize("status", ["disabled", "not_due", "deferred"])
def test_task_lifecycle_preserves_nonfailure_scheduler_outcomes(
    monkeypatch, collected_logs, status
):
    monkeypatch.setattr(
        tasks.scheduler, "run", lambda *args: {"status": status, "reason": "fixture reason"}
    )
    result = tasks.refresh_live_games.apply(task_id="deferred-fixture", throw=True)
    assert result.result["status"] == status
    rows = [row for row in collected_logs() if row.get("event") == "task_finished"]
    assert len(rows) == 1
    assert rows[0]["status"] == status and rows[0]["reason"] == "fixture reason"
    assert rows[0]["job"] == "live"
    assert rows[0]["level"] == "INFO"


def test_interrupted_task_logs_warning_and_resets_context(collected_logs):
    from nhl_web_app.logging_config import logged_task

    @logged_task("fixture")
    def interrupted():
        raise KeyboardInterrupt("fixture stop")

    with pytest.raises(KeyboardInterrupt):
        interrupted()
    row = collected_logs()[-1]
    assert row["status"] == "interrupted" and row["level"] == "WARNING"
    assert "KeyboardInterrupt" in row["traceback"]
    assert "job" not in context_fields()


def test_celery_logging_startup_keeps_shared_json_handlers():
    import os

    code = """
import django, logging
from nhl_web_app.celery_settings import app
django.setup()
app.log.setup_logging_subsystem(loglevel='INFO')
logging.getLogger('players.nhl_http').warning('after Celery setup')
logging.getLogger('celery.task').info('task logger after setup')
from celery.utils.log import get_multiprocessing_logger
get_multiprocessing_logger().warning('pool warning after setup')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "NHL_LOG_DESTINATION": "console"},
        capture_output=True,
        text=True,
        check=True,
    )
    rows = [json.loads(line) for line in result.stderr.splitlines()]
    assert [row["message"] for row in rows] == [
        "after Celery setup",
        "task logger after setup",
        "pool warning after setup",
    ]
