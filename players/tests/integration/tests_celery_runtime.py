"""Exercise the task entry point and database backend without a broker or live loaders."""

from unittest.mock import Mock, call

import pytest
from celery import states
from django_celery_results.backends.database import DatabaseBackend
from django_celery_results.models import TaskResult

from nhl_web_app.celery_settings import app
from players import tasks


pytestmark = pytest.mark.integration


def test_update_task_runs_loaders_in_order(monkeypatch):
    command = Mock()
    monkeypatch.setattr(tasks.management, "call_command", command)

    result = tasks.upd_database.apply(throw=True)

    assert result.successful()
    assert command.call_args_list == [call("upd_tms"), call("upd_pls"), call("upd_gms")]


@pytest.mark.parametrize("failed_command", ["upd_tms", "upd_pls", "upd_gms"])
def test_update_task_stops_when_a_loader_fails(monkeypatch, failed_command):
    def run(name):
        if name == failed_command:
            raise RuntimeError("synthetic loader failure")

    command = Mock(side_effect=run)
    monkeypatch.setattr(tasks.management, "call_command", command)

    with pytest.raises(RuntimeError, match="synthetic loader failure"):
        tasks.upd_database.apply(throw=True)

    order = ["upd_tms", "upd_pls", "upd_gms"]
    assert command.call_args_list == [
        call(name) for name in order[: order.index(failed_command) + 1]
    ]


@pytest.mark.django_db
def test_database_backend_updates_and_decodes_a_task_result():
    backend = DatabaseBackend(app=app)
    task_id = "synthetic-upgrade-result"
    backend.store_result(task_id, {"step": "players"}, states.STARTED)
    original_pk = TaskResult.objects.get(task_id=task_id).pk

    payload = {"loaded": 3, "details": [None, False, "München"]}
    backend.store_result(task_id, payload, states.SUCCESS)

    stored = TaskResult.objects.get(task_id=task_id)
    assert stored.pk == original_pk
    assert stored.status == states.SUCCESS
    result = backend.get_task_meta(task_id)
    assert result["status"] == states.SUCCESS
    assert result["result"] == payload
