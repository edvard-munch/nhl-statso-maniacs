# Locked uv workflow

`pyproject.toml` and `uv.lock` are the source of truth for Python dependencies.
Local commands, hooks and CI use `uv run --locked` / `uv sync --locked` so a stale
lockfile fails instead of silently resolving different versions. The first
metadata checkpoint preserved all 64 existing unique pins; the workflow switch
changes no dependency versions or supported Python versions.

## Setup and existing environments

Install [uv](https://docs.astral.sh/uv/getting-started/installation/). CI pins
**uv 0.10.10** via `astral-sh/setup-uv`; project metadata requires at least that
version. From the checkout root:

```bash
uv python install 3.12.16
make sync
make lock-check requirements-check check
uv pip check
```

uv creates `.venv/` with the interpreter in `.python-version`. Activation is
optional. If the old `venv/` is active, deactivate it first to avoid uv's mismatch
warning; project commands select `.venv/` regardless. Keep the old environment
until the replacement is verified; no command here deletes it or changes `.env`,
media or PostgreSQL data. Restart running app/worker processes with the new
interpreter. A shell alias that runs Django must also select it, for example:

```bash
alias django='uv run --locked python manage.py'
uv run --locked python manage.py runserver
make update-daily
```

Loader Make targets still support an intentional `PYTHON=/path/to/python` override;
the default is `uv run --locked python`. Ordered execution and stop-on-failure
behavior are unchanged. Python support stays at `>=3.12,<3.13`; patch selection is
3.12.16. Other platforms/interpreters are not validated by this migration.

## Dependency groups

The project is a private checkout application (`package = false`), without a build
or editable install of the app itself. Version `0.0.0` is a metadata placeholder,
not an application release.

| Selection | Contents |
| --- | --- |
| Project dependencies | Existing runtime/loader dependencies and retained transitive pins. Debug toolbar and Django extensions remain because settings load them unconditionally. |
| `test` | pytest, Django/coverage/request plugins and retained compatibility pins. |
| `hooks` | pre-commit. |
| `dev` (default) | Includes `test`, `hooks`, Ruff and the validated packaging tools. |

For an isolated trial, set `UV_PROJECT_ENVIRONMENT` to a dedicated absolute path.
For runtime-only deployment preparation in a separate environment:

```bash
UV_PROJECT_ENVIRONMENT=/absolute/path/to/runtime-env uv sync --locked --no-default-groups
uv pip check --python /absolute/path/to/runtime-env/bin/python
```

Use `--no-default-groups` with subsequent `uv run` commands for that runtime-only
environment too; otherwise default development tools are synced back in. Do not
point `UV_PROJECT_ENVIRONMENT` at shared/system Python: exact sync removes extra
packages. Isolated dependency builds remain enabled, with setuptools, wheel and
packaging constrained to the validated versions in `pyproject.toml`.

## Updating dependencies and compatibility export

Edit the appropriate dependency/group in `pyproject.toml` and regenerate the lock,
or use uv's group-aware dependency commands. Review version changes explicitly:

```bash
uv lock
uv sync --locked
make requirements
make requirements-check check
```

Commit metadata, lockfile and generated export together. Run Django system and
migration checks, offline coverage and Chromium with test-only credentials as
specified in [testing](testing.md). Do not run application loaders as a test.

`requirements.txt` is now a generated, hashed export of the default development
selection, including transitive/platform-conditional packages. It is retained for
pip compatibility and dependency scanners; do not edit it by hand. `make
requirements` regenerates it only after uv successfully exports the locked graph.
`make requirements-check` checks exact agreement without writing the file, and CI
runs this check. `requirements-bootstrap.txt` and `requirements-hooks.txt` are
retired; older checkpoint instructions mentioning them describe historical setups.
The uv lockfile and its build constraints are authoritative for supported installs.

## Hooks and CI

After configuring `test-database.local.json` with a dedicated test role, reinstall
hooks in each clone:

```bash
make hooks
make hooks-run
make hooks-run-push
```

`make hooks` installs launchers using the locked pre-commit environment. Local test
hooks use `language: system`; uv must be on PATH for terminal and GUI Git clients.
The runner invokes uv directly for pytest, without searching old/active venvs or
falling back if uv/sync fails. Ruff retains its pinned managed hook environment.
Only the dedicated JSON configuration supplies test credentials; application
credentials and inherited pytest selection flags cannot override it.

CI installs Python from `.python-version`, pins uv 0.10.10, caches by `uv.lock`,
syncs with `--locked`, checks dependencies/export drift and runs existing lint,
JavaScript, Django/migration, offline coverage and Chromium checks. Coverage XML
and browser failure artifacts keep their existing conditional uploads. Node and
Playwright remain managed separately in `browser/package-lock.json`.

## Validation

The metadata checkpoint verified identical pip/uv versions for 74 installed
packages and runtime-only startup with 45 packages. The workflow checkpoint
validates a clean sync, the actual Make commands, generated export checks and
real commit/push test hooks installed in a temporary Git checkout. An activated
legacy venv cannot select the test interpreter. Synthetic fixtures and disposable
PostgreSQL isolate all data; no actual commit/push or application loader is run.
Both installed test hooks pass, as do the Make coverage target (**902 offline
tests**, **90.86% combined coverage**, unchanged 35% gate), **21 Chromium cases**
and coverage XML export. Missing-uv/legacy-venv regressions, a PATH without a
`python` command, stale-lock blocking, export drift/failure preservation and loader
order/stop-on-failure checks pass. Workflow/hook YAML, action inputs, shell syntax,
Ruff and JavaScript syntax are checked locally.
Hosted Actions verification still requires pushing this commit. Deployment
backup/restore rehearsal, optional live API repairs and legacy cleanup remain
separate work.
