"""Django must start from a checkout without pre-created runtime directories."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[4]


def test_clean_checkout_logging_starts_without_existing_log_directory(tmp_path):
    checkout = tmp_path / "nhl-statso-maniacs"
    checkout.mkdir()
    shutil.copytree(
        str(ROOT / "nhl_web_app"),
        str(checkout / "nhl_web_app"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    assert not (checkout / "logs").exists()
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(checkout) + os.pathsep + str(ROOT),
        DJANGO_SETTINGS_MODULE="nhl_web_app.settings",
        DEBUG="false",
        SECRET_KEY="startup-test-only",
        ALLOWED_HOSTS="localhost,testserver",
        POSTGRES_DB="unused_startup_test",
        POSTGRES_USER="unused_startup_role",
        POSTGRES_DB_PASSWORD="unused",
        EMAIL_HOST_USER="test@example.invalid",
        EMAIL_PASSWORD="unused",
    )
    code = """
import logging
import django
import requests
from django.db.backends.base.base import BaseDatabaseWrapper

def forbidden(*args, **kwargs):
    raise AssertionError('Startup must not access a database or HTTP endpoint')

BaseDatabaseWrapper.connect = forbidden
requests.sessions.Session.request = forbidden
for index in range(2):
    django.setup()
    logging.getLogger('django').info('Clean startup %s', index)
logging.shutdown()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(checkout),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert result.returncode == 0, result.stderr
    log = (checkout / "logs/nhl_web_app.log").read_text()
    assert "Clean startup 0" in log
    assert "Clean startup 1" in log
