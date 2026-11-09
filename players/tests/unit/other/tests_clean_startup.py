"""Django must start from a checkout without pre-created runtime directories."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("destination", ["file", "console"])
def test_clean_checkout_logging_starts_without_existing_log_directory(tmp_path, destination):
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
        NHL_LOG_DESTINATION=destination,
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
import importlib.abc
import logging
import sys
import django
import requests

class NoMySQLDriver(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pymysql', 'MySQLdb'}:
            raise AssertionError('PostgreSQL startup must not import a MySQL driver')

sys.meta_path.insert(0, NoMySQLDriver())
from django.db.backends.base.base import BaseDatabaseWrapper

def forbidden(*args, **kwargs):
    raise AssertionError('Startup must not access a database or HTTP endpoint')

BaseDatabaseWrapper.connect = forbidden
requests.sessions.Session.request = forbidden
for index in range(2):
    django.setup()
    logging.getLogger('django').info('Clean startup %s', index)
from nhl_web_app import celery_app
from nhl_web_app.celery_settings import app
from nhl_web_app.wsgi import application
from django.db import connections
assert celery_app is app
assert callable(application)
assert connections['default'].vendor == 'postgresql'
assert connections['default'].Database.__name__.startswith('psycopg')
assert not {'pymysql', 'MySQLdb'} & sys.modules.keys()
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
    if destination == "file":
        log = (checkout / "logs/nhl_web_app.log").read_text()
    else:
        assert not (checkout / "logs").exists()
        log = result.stderr
    assert "Clean startup 0" in log
    assert "Clean startup 1" in log
