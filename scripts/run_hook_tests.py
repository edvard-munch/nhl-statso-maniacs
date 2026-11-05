"""Run offline or browser tests with explicit, test-only database credentials."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
CONFIG_VARIABLE = "NHL_TEST_DATABASE_CONFIG"
CONFIG_FILENAME = "test-database.local.json"
TEST_DATABASE_PREFIX = "nhl_test_"
CONFIG_ERROR_EXIT = 2
COVERAGE_THRESHOLD = 35
MIN_PORT = 1
MAX_PORT = 65535
REQUIRED_FIELDS = {"name", "user", "password"}
DEFAULT_FIELDS = {"host": "localhost", "port": "5432"}
SETTINGS_MODULE = "nhl_web_app.hook_test_settings"


def load_database(config_path):
    try:
        config = json.loads(config_path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(
            "Cannot read test database configuration. Copy test-database.example.json "
            "to test-database.local.json and configure a dedicated test role."
        ) from error
    if not isinstance(config, dict) or not REQUIRED_FIELDS.issubset(config):
        raise ValueError("Test database configuration requires name, user and password.")
    if set(config) - REQUIRED_FIELDS - set(DEFAULT_FIELDS):
        raise ValueError("Unknown test database configuration field.")
    database = dict(DEFAULT_FIELDS, **config)
    if any(not isinstance(value, str) for value in database.values()):
        raise ValueError("Test database configuration values must be strings.")
    if not database["name"].startswith(TEST_DATABASE_PREFIX) or not database["user"]:
        raise ValueError("Use a dedicated role and a database name beginning with nhl_test_.")
    if not database["host"] or not database["port"].isdigit():
        raise ValueError("A test database host and numeric port are required.")
    if not MIN_PORT <= int(database["port"]) <= MAX_PORT:
        raise ValueError("Invalid test database port.")
    return database


def project_python():
    executable = Path("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Pre-commit's managed Python only launches this standard-library runner.
    # Tests must use the project environment, not the managed hook environment.
    candidates = [ROOT / directory / executable for directory in ("venv", ".venv")]
    if os.environ.get("VIRTUAL_ENV"):
        candidates.append(Path(os.environ["VIRTUAL_ENV"]) / executable)
    return str(next((path for path in candidates if path.is_file()), Path(sys.executable)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--coverage", action="store_true")
    mode.add_argument("--browser", action="store_true")
    options = parser.parse_args(argv)
    config_path = Path(os.environ.get(CONFIG_VARIABLE, str(ROOT / CONFIG_FILENAME))).expanduser()
    try:
        database = load_database(config_path)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return CONFIG_ERROR_EXIT

    env = os.environ.copy()
    # Application settings are imported for parity, but never receive app DB credentials.
    env.update(
        POSTGRES_DB=database["name"],
        POSTGRES_USER=database["user"],
        POSTGRES_DB_PASSWORD=database["password"],
        DJANGO_SETTINGS_MODULE=SETTINGS_MODULE,
        DEBUG="false",
        SECRET_KEY="hook-tests-only",
        ALLOWED_HOSTS="localhost,127.0.0.1,testserver",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST_USER="hooks@example.invalid",
        EMAIL_PASSWORD="unused",
    )
    env.update({"NHL_TEST_DB_" + key.upper(): value for key, value in database.items()})
    # Inherited flags must not narrow the suite, enable live tests, or bypass migrations.
    env.pop("PYTEST_ADDOPTS", None)
    command = [
        project_python(),
        "-m",
        "pytest",
        "-c",
        str(ROOT / "players/tests/pytest.ini"),
        "--ds=" + SETTINGS_MODULE,
        "-m",
        "browser and not external" if options.browser else "not external and not browser",
    ]
    if options.coverage:
        command.extend(
            [
                "--cov=players",
                "--cov-config=" + str(ROOT / ".coveragerc"),
                "--cov-report=term-missing",
                "--cov-fail-under={}".format(COVERAGE_THRESHOLD),
            ]
        )
    command.append(str(ROOT / "players/tests"))
    return subprocess.call(command, cwd=str(ROOT), env=env)


if __name__ == "__main__":
    sys.exit(main())
