"""Export or check the reviewed OpenAPI contract without application configuration."""

import argparse
from contextlib import ExitStack
from io import StringIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import NamedTemporaryFile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "api" / "openapi.json"
SETTINGS_MODULE = "nhl_web_app.schema_settings"
DRIFT_EXIT = 1
GENERATION_EXIT = 2
GENERATE_FLAG = "--generate-offline"
# Do not pass deployment credentials, Django/Python overrides or scheduler flags.
PLATFORM_ENVIRONMENT = frozenset(
    {"PATH", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "TMPDIR", "TMP", "TEMP"}
)
SCHEMA_ENVIRONMENT = {
    "DJANGO_SETTINGS_MODULE": SETTINGS_MODULE,
    "PYTHONHASHSEED": "0",
    "PYTHONUTF8": "1",
}


class OfflineSchemaAccessError(RuntimeError):
    """Schema introspection attempted to access data or network services."""


def forbidden_access(*args, **kwargs):
    raise OfflineSchemaAccessError("OpenAPI export cannot access databases, network or .env files.")


def canonical_schema(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def generate_offline():
    """Only called by the isolated child, before Django settings/apps are loaded."""
    with ExitStack() as guards:
        guards.enter_context(patch.object(sys, "path", [str(ROOT), *sys.path]))
        guards.enter_context(patch.object(socket.socket, "connect", forbidden_access))
        guards.enter_context(patch.object(socket.socket, "connect_ex", forbidden_access))
        guards.enter_context(patch.object(socket, "getaddrinfo", forbidden_access))
        guards.enter_context(patch.object(socket, "create_connection", forbidden_access))
        import environ
        from django.db.backends.base.base import BaseDatabaseWrapper
        import django

        guards.enter_context(patch.object(environ.Env, "read_env", forbidden_access))
        guards.enter_context(patch.object(BaseDatabaseWrapper, "connect", forbidden_access))
        django.setup()
        from django.core.management import call_command

        output = StringIO()
        call_command(
            "spectacular", "--format", "openapi-json", "--validate", "--fail-on-warn", stdout=output
        )
        return canonical_schema(json.loads(output.getvalue()))


def write_schema(content):
    """Publish a complete artifact; failures never truncate the reviewed copy."""
    SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=SCHEMA.parent, prefix=".openapi-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        temporary.replace(SCHEMA)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail on drift without changing files.")
    mode.add_argument(GENERATE_FLAG, action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if options.generate_offline:
        sys.stdout.buffer.write(generate_offline())
        return 0

    env = {key: value for key, value in os.environ.items() if key in PLATFORM_ENVIRONMENT}
    env.update(SCHEMA_ENVIRONMENT)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), GENERATE_FLAG],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    try:
        content = canonical_schema(json.loads(result.stdout))
    except (TypeError, ValueError):
        print(
            "OpenAPI generation returned invalid JSON; the reviewed schema was not changed.",
            file=sys.stderr,
        )
        return GENERATION_EXIT
    if options.check:
        if not SCHEMA.is_file() or SCHEMA.read_bytes() != content:
            print(
                "api/openapi.json is missing or stale. Run make schema and review the diff.",
                file=sys.stderr,
            )
            return DRIFT_EXIT
    else:
        write_schema(content)
        print("Updated api/openapi.json. Review its diff with the API changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
