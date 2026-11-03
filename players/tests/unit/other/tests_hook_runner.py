"""Hook configuration must never silently reuse application database credentials."""

import json
import os
from pathlib import Path

import pytest

from scripts import run_hook_tests as runner


pytestmark = pytest.mark.unit


@pytest.fixture
def database_config(tmp_path):
    path = tmp_path / "database.json"
    path.write_text(
        json.dumps({"name": "nhl_test_fixture", "user": "test_role", "password": "test-secret"})
    )
    return path


@pytest.mark.parametrize("coverage", [False, True])
def test_runner_uses_explicit_test_credentials_and_preserves_exit_code(
    monkeypatch, database_config, coverage
):
    monkeypatch.setenv(runner.CONFIG_VARIABLE, str(database_config))
    monkeypatch.setenv("POSTGRES_DB", "application")
    monkeypatch.setenv("POSTGRES_USER", "application-role")
    monkeypatch.setenv("POSTGRES_DB_PASSWORD", "application-secret")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--nomigrations -m external --lf")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "unrelated_settings")
    monkeypatch.setattr(runner, "project_python", lambda: "selected-python")
    calls = []

    def run(command, cwd, env):
        calls.append(command)
        assert cwd == str(runner.ROOT)
        assert env["POSTGRES_DB"] == env["NHL_TEST_DB_NAME"] == "nhl_test_fixture"
        assert env["POSTGRES_USER"] == env["NHL_TEST_DB_USER"] == "test_role"
        assert env["POSTGRES_DB_PASSWORD"] == env["NHL_TEST_DB_PASSWORD"] == "test-secret"
        assert env["NHL_TEST_DB_HOST"] == "localhost"
        assert env["NHL_TEST_DB_PORT"] == "5432"
        assert env["DJANGO_SETTINGS_MODULE"] == runner.SETTINGS_MODULE
        assert "PYTEST_ADDOPTS" not in env
        assert "--ds=" + runner.SETTINGS_MODULE in command
        assert command[command.index("-m", 2) + 1] == "not external"
        assert command[-1] == str(runner.ROOT / "players/tests")
        assert command[0] == "selected-python"
        assert ("--cov-fail-under=35" in command) is coverage
        return 7

    monkeypatch.setattr(runner.subprocess, "call", run)
    assert runner.main(["--coverage"] if coverage else []) == 7
    assert len(calls) == 1
    assert runner.load_database(database_config)["password"] == "test-secret"
    assert os.environ["POSTGRES_DB"] == "application"


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "[]",
        "{}",
        '{"name":"app","user":"role","password":"secret"}',
        '{"name":"nhl_test_base","user":"","password":"secret"}',
        '{"name":"nhl_test_base","user":"role","password":123}',
        '{"name":"nhl_test_base","user":"role","password":"secret","port":"0"}',
        '{"name":"nhl_test_base","user":"role","password":"secret","port":"abc"}',
    ],
)
def test_bad_configuration_blocks_tests_without_exposing_values(
    monkeypatch, tmp_path, capsys, content
):
    path = tmp_path / "bad.json"
    path.write_text(content)
    monkeypatch.setenv(runner.CONFIG_VARIABLE, str(path))

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid configuration must not start pytest")

    monkeypatch.setattr(runner.subprocess, "call", unexpected)
    assert runner.main([]) == runner.CONFIG_ERROR_EXIT
    assert "secret" not in capsys.readouterr().err


def test_missing_configuration_does_not_fall_back_to_application(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(runner.CONFIG_VARIABLE, str(tmp_path / "missing.json"))
    monkeypatch.setenv("POSTGRES_DB", "application")
    monkeypatch.setattr(
        runner.subprocess, "call", lambda *args, **kwargs: pytest.fail("Must not run")
    )
    assert runner.main([]) == runner.CONFIG_ERROR_EXIT
    assert "test-database.example.json" in capsys.readouterr().err


def test_project_python_finds_repository_venv_without_activation(monkeypatch, tmp_path):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    executable = Path("Scripts/python.exe" if runner.os.name == "nt" else "bin/python")
    python = tmp_path / "venv" / executable
    python.parent.mkdir(parents=True)
    python.touch()
    assert runner.project_python() == str(python)


def test_project_python_ignores_managed_hook_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    executable = Path("Scripts/python.exe" if runner.os.name == "nt" else "bin/python")
    project = tmp_path / "venv" / executable
    managed = tmp_path / "managed-hook" / executable
    for path in (project, managed):
        path.parent.mkdir(parents=True)
        path.touch()
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "managed-hook"))
    assert runner.project_python() == str(project)
