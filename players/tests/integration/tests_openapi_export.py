"""The checked contract matches real routes and exports from a clean offline copy."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from django.urls import reverse
import pytest

from scripts import export_openapi as exporter

pytestmark = pytest.mark.integration


def test_reviewed_schema_matches_public_endpoint_without_database_or_http(client, requests_mock):
    # No django_db marker: pytest's database blocker remains enabled.
    response = client.get(reverse("api_v1:schema"))
    assert response.status_code == 200
    assert response.json() == json.loads(exporter.SCHEMA.read_bytes())
    assert not requests_mock.called


def test_clean_checkout_export_and_drift_check_are_environment_independent(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for name in ("nhl_web_app", "players", "users", "scripts"):
        shutil.copytree(
            exporter.ROOT / name,
            checkout / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "migrations"),
        )
    target = checkout / "api" / "openapi.json"
    script = checkout / "scripts" / "export_openapi.py"
    # Invalid operator configuration must neither be read nor echoed by export.
    (checkout / ".env").write_text("NHL_LIVE_SECONDS=invalid-operator-value\n")
    # A copied checkout is a fixture, not a second coverage source tree.
    # pytest-cov's startup hook would otherwise register its unexecuted players
    # package and merge those duplicate paths into the main suite's report.
    inherited = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_"))
    }
    environment = dict(
        inherited,
        DJANGO_SETTINGS_MODULE="invalid.application.settings",
        PYTHONHASHSEED="123",
        NHL_LIVE_SECONDS="invalid-operator-value",
        NHL_LOG_DESTINATION="invalid",
    )

    def run(*args):
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=checkout,
            env=environment,
            capture_output=True,
            text=True,
        )

    missing = run("--check")
    assert missing.returncode == 1, missing.stderr
    assert not target.exists()
    generated = run()
    assert generated.returncode == 0, generated.stderr
    assert "invalid-operator-value" not in generated.stdout + generated.stderr
    assert target.read_bytes() == exporter.SCHEMA.read_bytes()
    assert not (checkout / "logs").exists()
    before = target.stat().st_mtime_ns
    environment.update(PYTHONHASHSEED="456", SECRET_KEY="different-environment-key")
    checked = run("--check")
    assert checked.returncode == 0, checked.stderr
    assert target.stat().st_mtime_ns == before
    assert not (checkout / "logs").exists()
    target.write_bytes(target.read_bytes().replace(b'"1.0.0"', b'"stale-version"', 1))
    stale = target.read_bytes()
    drift = run("--check")
    assert drift.returncode == 1 and "make schema" in drift.stderr
    assert target.read_bytes() == stale
    assert str(checkout).encode() not in exporter.SCHEMA.read_bytes()
