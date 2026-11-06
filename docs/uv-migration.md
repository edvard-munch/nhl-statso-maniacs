# uv migration: metadata and lockfile checkpoint

This first checkpoint adds project metadata and `uv.lock` alongside the working
pip workflow. README setup, Make targets, CI and commit/push hooks still use the
existing requirements files and project venv. Do not replace that environment yet.

## Dependency layout

`pyproject.toml` describes a private checkout-based application, not an installable
distribution (`tool.uv.package = false`). Its `0.0.0` version is a metadata
placeholder, not an application release. Python support is limited to the validated
3.12 minor (`>=3.12,<3.13`); `.python-version` selects 3.12.16. Other interpreters
and operating systems have not been validated by this checkpoint.

| Selection | Contents |
| --- | --- |
| Project dependencies | Existing application/loader dependencies, including their pinned transitive dependencies. Debug toolbar and Django extensions remain here because settings load them unconditionally. |
| `test` group | pytest, Django/coverage/request plugins and the retained test compatibility pins. |
| `hooks` group | The existing pre-commit pin. |
| `dev` group (default) | Includes `test` and `hooks`, Ruff, retained legacy lint tools and the validated pip/setuptools/wheel/packaging tools. |

All 64 unique pins from `requirements.txt`, `requirements-hooks.txt` and
`requirements-bootstrap.txt` are preserved exactly. Grouping is not a removal
audit: legacy compatibility/tool pins remain for a separate review. Until the
workflow switches, dependency edits must keep those files and the metadata in
agreement, then regenerate/check the lockfile. The lock records transitive
versions, platform markers and artifact hashes from public PyPI. Isolated source
builds constrain setuptools, wheel and packaging to the validated bootstrap pins;
build isolation remains enabled.

## Opt-in validation

Validated with uv 0.10.10 and Python 3.12.16 on Linux/PostgreSQL 16. The metadata
requires uv 0.10.10 or newer. Follow the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)
if needed. From the project root, check the lock without changing the project venv:

```bash
uv --version
uv lock --check --python 3.12.16
```

Use a separate temporary environment for a trial sync:

```bash
(
  uv_trial_dir="$(mktemp -d)"
  export UV_PROJECT_ENVIRONMENT="$uv_trial_dir/venv"
  uv sync --locked --python 3.12.16
  uv run --locked --no-sync python -m pip check
  uv sync --locked --check
)
```

The temporary directory may be removed after the trial. `--locked` fails rather
than silently updating a stale lockfile; do not substitute `--frozen` for this
check. To select runtime dependencies alone, use a different temporary environment
with `uv sync --locked --no-default-groups`. This environment intentionally lacks
pytest, pre-commit, Ruff and pip; use `uv pip check --python /path/to/venv/bin/python`
for its dependency check. Default `.venv/` is ignored, but the explicit temporary
path above avoids creating it during this checkpoint.

Existing hook runner interpreter selection prefers `venv` over `.venv` and the
active environment. Calling it through `uv run` does not yet switch its tests to
the uv interpreter. The migration validation explicitly selected each temporary
interpreter and dedicated PostgreSQL configuration, without changing that runner
or connecting to application data. Continue using the normal setup and hooks.

## Verification and next commit

The clean default sync installs the same 74 package versions as the validated
pip environment; a separate runtime-only sync installs 45 packages without test,
hook or lint tools. Both pass dependency and offline lock/sync consistency checks.
Runtime-only Django system/migration checks and WSGI/Celery startup pass against
disposable PostgreSQL. The default environment passes Django checks, **902 offline
tests** at **90.86% combined coverage** (35% gate unchanged), and **21 Chromium
tests**, without warnings. No application data or live NHL services are accessed.
Node/Playwright assets remain outside this Python lockfile.

Next: switch environment/interpreter selection, Make commands, hooks and CI to the
locked workflow; update normal setup instructions and reconcile the transitional
requirements files. Validate that change separately. Interpreter, dependency
upgrades, optional live API repairs and legacy removal remain separate work.
