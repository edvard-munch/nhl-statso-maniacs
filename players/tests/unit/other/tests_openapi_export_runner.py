"""Reviewed-schema writes are deterministic, isolated and fail without data loss."""

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import export_openapi as exporter

pytestmark = pytest.mark.unit


@pytest.fixture
def schema_file(monkeypatch, tmp_path):
    target = tmp_path / "api" / "openapi.json"
    monkeypatch.setattr(exporter, "SCHEMA", target)
    return target


@pytest.fixture
def generation(monkeypatch):
    result = SimpleNamespace(returncode=0, stdout='{"z": "é", "a": {"c": 1}}', stderr="")
    monkeypatch.setattr(exporter.subprocess, "run", lambda *args, **kwargs: result)
    return result


def test_export_creates_canonical_utf8_json_with_lf_and_no_temporary_files(schema_file, generation):
    assert exporter.main([]) == 0
    assert schema_file.read_bytes() == '{\n  "a": {\n    "c": 1\n  },\n  "z": "é"\n}\n'.encode()
    assert list(schema_file.parent.iterdir()) == [schema_file]


@pytest.mark.parametrize("existing", [None, b"reviewed schema\n"])
def test_check_detects_missing_or_stale_copy_without_writing(
    schema_file, generation, capsys, existing
):
    if existing is not None:
        schema_file.parent.mkdir()
        schema_file.write_bytes(existing)
    assert exporter.main(["--check"]) == exporter.DRIFT_EXIT
    assert "make schema" in capsys.readouterr().err
    assert (schema_file.read_bytes() if schema_file.exists() else None) == existing
    if existing is None:
        assert not schema_file.parent.exists()


def test_matching_check_does_not_rewrite_artifact(schema_file, generation):
    assert exporter.main([]) == 0
    before = schema_file.stat().st_mtime_ns
    assert exporter.main(["--check"]) == 0
    assert schema_file.stat().st_mtime_ns == before


@pytest.mark.parametrize("mode", [[], ["--check"]])
def test_validation_failure_preserves_reviewed_copy_and_exit_code(
    schema_file, generation, capsys, mode
):
    schema_file.parent.mkdir()
    schema_file.write_bytes(b"reviewed copy\n")
    generation.returncode = 7
    generation.stderr = "Schema validation failed\n"
    assert exporter.main(mode) == 7
    assert schema_file.read_bytes() == b"reviewed copy\n"
    assert capsys.readouterr().err == "Schema validation failed\n"


@pytest.mark.parametrize("content", ["not JSON", "", '{"default": NaN}'])
def test_invalid_or_nonfinite_generation_cannot_overwrite_reviewed_copy(
    schema_file, generation, capsys, content
):
    schema_file.parent.mkdir()
    schema_file.write_bytes(b"reviewed copy\n")
    generation.stdout = content
    assert exporter.main([]) == exporter.GENERATION_EXIT
    assert schema_file.read_bytes() == b"reviewed copy\n"
    assert "invalid JSON" in capsys.readouterr().err


def test_failed_atomic_publish_preserves_copy_and_cleans_temp_file(
    monkeypatch, schema_file, generation
):
    schema_file.parent.mkdir()
    schema_file.write_bytes(b"reviewed copy\n")

    def fail(*args):
        raise OSError("fixture publish failure")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="fixture publish failure"):
        exporter.main([])
    assert schema_file.read_bytes() == b"reviewed copy\n"
    assert list(schema_file.parent.iterdir()) == [schema_file]


def test_child_environment_excludes_application_and_python_configuration(
    monkeypatch, schema_file, generation
):
    for key in (
        "SECRET_KEY",
        "POSTGRES_DB",
        "CELERY_BROKER_URL",
        "PYTHONPATH",
        "NHL_LIVE_SECONDS",
        "COV_CORE_SOURCE",
        "COVERAGE_PROCESS_START",
    ):
        monkeypatch.setenv(key, "application-value")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "application.settings")
    monkeypatch.setenv("PYTHONHASHSEED", "random")
    monkeypatch.setenv("PATH", "/fixture/bin")

    def run(command, cwd, env, **kwargs):
        assert command == [
            exporter.sys.executable,
            str(Path(exporter.__file__).resolve()),
            exporter.GENERATE_FLAG,
        ]
        assert cwd == exporter.ROOT
        assert env["PATH"] == "/fixture/bin"
        assert env["DJANGO_SETTINGS_MODULE"] == "nhl_web_app.schema_settings"
        assert env["PYTHONHASHSEED"] == "0" and env["PYTHONUTF8"] == "1"
        assert "application-value" not in env.values()
        assert set(env) <= exporter.PLATFORM_ENVIRONMENT | exporter.SCHEMA_ENVIRONMENT.keys()
        return generation

    monkeypatch.setattr(exporter.subprocess, "run", run)
    assert exporter.main([]) == 0
    assert os.environ["POSTGRES_DB"] == "application-value"


@pytest.mark.parametrize(
    "resource", ["database", "connect", "connect_ex", "dns", "connection", "dotenv"]
)
def test_generation_guards_block_external_access_before_app_setup(monkeypatch, resource):
    import django
    import environ
    import socket
    from django.db.backends.base.base import BaseDatabaseWrapper

    targets = {
        "database": (BaseDatabaseWrapper, "connect", (None,)),
        "connect": (socket.socket, "connect", (None, ("127.0.0.1", 1))),
        "connect_ex": (socket.socket, "connect_ex", (None, ("127.0.0.1", 1))),
        "dns": (socket, "getaddrinfo", ("api.nhle.com", 443)),
        "connection": (socket, "create_connection", (("127.0.0.1", 1),)),
        "dotenv": (environ.Env, "read_env", ("/fixture/.env",)),
    }
    target, name, args = targets[resource]

    def unexpected(*args, **kwargs):
        pytest.fail("Offline guard must replace external access")

    monkeypatch.setattr(target, name, unexpected)
    monkeypatch.setattr(django, "setup", lambda: getattr(target, name)(*args))
    before = list(exporter.sys.path)
    with pytest.raises(exporter.OfflineSchemaAccessError, match="cannot access"):
        exporter.generate_offline()
    assert exporter.sys.path == before
    assert getattr(target, name) is unexpected


@pytest.mark.parametrize("enabled, calls", [(None, 1), ("false", 0)])
def test_dotenv_opt_out_keeps_normal_startup_default(monkeypatch, tmp_path, enabled, calls):
    import environ

    root = tmp_path / "checkout"
    package = root / "nhl_web_app"
    package.mkdir(parents=True)
    source = package / "environ.py"
    source.write_bytes((exporter.ROOT / "nhl_web_app" / "environ.py").read_bytes())
    (root / ".env").write_text("fixture-only\n")
    if enabled is None:
        monkeypatch.delenv("NHL_READ_ENV_FILE", raising=False)
    else:
        monkeypatch.setenv("NHL_READ_ENV_FILE", enabled)
    seen = []
    monkeypatch.setattr(environ.Env, "read_env", lambda filename: seen.append(filename))
    spec = importlib.util.spec_from_file_location("fixture_environment", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert seen == [str(root / ".env")] * calls
