# NHL Web App

NHL web app for tracking player stats, game data, favorites, and player comparisons.

The [modernization roadmap](docs/modernization-roadmap.md) records completed work,
remaining test gaps, and the planned Python/Django upgrade sequence.
The [legacy inventory](docs/legacy-audit.md) records command callers, dependency
cleanup candidates and usage that must be confirmed outside the repository.
The proposed [frontend architecture and migration plan](docs/frontend-architecture.md)
and [API conventions](docs/api-conventions.md) describe the next development phase;
Vue/Vite is selected; frontend scaffolding is not implemented yet. The [JSON API foundation](docs/api-conventions.md#implemented-api-foundation)
now provides versioned routing and an OpenAPI schema. The
[saved scoreboard endpoint](docs/scoreboard-api.md) is available at
`/api/v1/games/?date=YYYY-MM-DD`, with [saved game details](docs/game-detail-api.md)
at `/api/v1/games/{nhl_id}/`. Loaded seasons are available at `/api/v1/seasons/`; see the
[seasons contract](docs/seasons-api.md). The selected-season Players catalogue is
available at `/api/v1/players/`; see its [contract](docs/players-api.md).
[Team metadata and season contributions](docs/teams-api.md) are available under
`/api/v1/teams/`. Typed [player profiles, season histories and gamelogs](docs/player-profile-api.md)
are available under `/api/v1/players/{player_type}/{nhl_id}/`. Remaining JSON APIs will be implemented
before frontend scaffolding.
Documentation is maintained as Markdown files in `docs/`; no Sphinx build is
required. The obsolete Sphinx setup and its unused dependencies have been retired.

## Stack

- Python 3.12.16
- Django 5.2.18 LTS
- PostgreSQL 14+ (validated with PostgreSQL 16)

Django 5.2 is the planned LTS endpoint of the staged upgrade. See
[upgrade progress and validation](docs/django-upgrade-checkpoints.md).

## Local Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (CI uses
0.10.10; the project requires at least that version). From the project root:

```bash
uv python install 3.12.16
uv sync --locked
uv run --locked python --version
```

uv creates `.venv/` using `.python-version`. Activation is optional: Make targets
and `uv run --locked` select it even if an old `venv/` is activated. Keep uv on
PATH in terminal and Git GUI environments. Restart app/worker processes using the
new environment. Existing `.env` and PostgreSQL data are retained.

`pyproject.toml` and `uv.lock` are authoritative; `requirements.txt` is a generated
pip compatibility export. See the [uv workflow](docs/uv-migration.md) for dependency
updates, runtime-only installs and migration from the old environment.

## Code Quality

This project uses Ruff for formatting and linting.

```bash
make format
make lint
make check
```

Local commit/push hooks run formatting/lint and the offline tests before a
commit, then lint and the coverage gate before a push. One-time setup per clone:

```bash
uv sync --locked
cp test-database.example.json test-database.local.json
# Edit test-database.local.json with your dedicated test-role credentials.
make hooks
```

Create the test role/database and validate the setup as described in
[local hook setup](docs/testing.md#local-commit-and-push-hooks). The local JSON file
is ignored by Git; hooks do not fall back to application database credentials.
GitHub CI independently checks pushed code. Branch protection is a separate
repository setting.


## Environment Variables

Copy the local development example to `.env` in the project root (preserve any
existing configuration):

```bash
cp -n .env.example .env
```

If `.env` already exists but is empty, copy the example's contents into it.
Set `SECRET_KEY` to a random value and replace the PostgreSQL values with your
local database name, role, and password. For example, generate a secret with
`uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(50))'`.
The example uses `ALLOWED_HOSTS=localhost,127.0.0.1,[::1]` and sends development
email to the console, so email credentials can be empty.

The loader finds `.env` relative to the project files; existing shell environment
variables take precedence. A `Set the ALLOWED_HOSTS environment variable` error
means that key is missing from both sources.

The supported keys are:

- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_DB_PASSWORD`
- `STATIC_URL`
- `MEDIA_URL`
- `EMAIL_BACKEND`
- `EMAIL_HOST_USER`
- `EMAIL_PASSWORD`

Optional server automation also reads `CELERY_BROKER_URL`,
`NHL_SCHEDULING_ENABLED` and the `NHL_*` cadence/window settings documented in
[Celery operation](docs/celery-operations.md). NHL schedules default to disabled.

## Database Setup

```bash
uv run --locked python manage.py migrate
uv run --locked python manage.py createsuperuser
```

## Populate NHL Data

From the project root, run the daily sequence in the locked environment with:

```bash
make update-daily
```

This runs `upd_pls` → `upd_pls_tot --mode=current` → `upd_gms` in order.
For a routine refresh that also updates team metadata (typically weekly), use:

```bash
make update-all
```

`update-all` runs `upd_tms` first, then the daily sequence. Both targets stop at
the first failed command, including when using `make -j`. Earlier successful
loaders remain committed; the sequence is not a single database transaction.
After resolving a failure, rerun the target. Terminal output includes each command
and its existing progress output. Historical full mode remains separate below.

The default loader interpreter is `uv run --locked python`. For an intentional
interpreter override:

```bash
make update-daily PYTHON=/path/to/python
```

Run update commands in this order for regular updates:

```bash
uv run --locked python manage.py upd_tms
uv run --locked python manage.py upd_pls
uv run --locked python manage.py upd_pls_tot --mode=current
uv run --locked python manage.py upd_gms
```

`upd_pls` updates player metadata, ordinary statistics columns, and the current
season's `sbs_stats` / `sbs_stats_avg` rows together. It can add a new season without
a full historical refresh. Reports are fetched and validated before the database
update; a failed report leaves the previous statistics intact. Players absent
from the season's reports keep their historical data.

Run a full player totals rebuild only when needed:

```bash
make update-history
```

This runs `upd_pls_tot --mode=full` for occasional historical refreshes/backfills.
It makes heavier player landing calls and stays separate from routine update targets.

Current mode also creates or refreshes season rows directly from NHL reports,
without player landing calls. Full mode refreshes profile/career data from landing
responses and season statistics from reports, including separate team contributions
for traded players. See [season loader behavior and tests](docs/season-statistics-loaders.md).

The legacy projection, video, season experiment and fixture-export commands are
retired. Existing projection/video data and profile display are preserved; see
the [artifact/dependency follow-up review](docs/legacy-audit.md#separate-reviews-after-top-level-command-retirement).

For game-response failures and safe reruns, see [game-loader behavior](docs/game-loading.md).
Supported loader GETs use bounded retries with `Retry-After` cooldowns; persistent rate
limits stop the sequence. See [shared HTTP policy and reruns](docs/loader-http.md).

## Update Cadence

- `upd_tms`: run weekly to keep team metadata current.
- `upd_pls`, `upd_gms`: run frequently (for example daily).
- `upd_pls_tot --mode=current`: run frequently to refresh current-season and career aggregates without heavy landing calls.
- `upd_pls_tot --mode=full`: run occasionally for historical refresh/backfill.

For the planned always-on server, see the [scheduling policy and server
requirements](docs/loader-scheduling.md). It separates frequent targeted live-game
refreshes from daily season/career work and weekly team updates. Separate tasks
and configurable UTC schedules are implemented but opt-in. See
[broker, worker and Beat setup](docs/celery-operations.md); the legacy task remains
available separately and is not scheduled.

For a bounded game refresh, use a date or game ID, optionally filtering states:

```bash
uv run --locked python manage.py upd_gms --date 2026-11-08 --state active
uv run --locked python manage.py upd_gms --game-id 2023020001
```

Repeat the same selector for multiple dates/IDs. Targets can replay finished
games; known pregame games are deferred. See [targeted refresh behavior](docs/game-loading.md#targeted-game-and-date-refreshes)
for per-game transactions, completion flags and unavailable report fields.

Loader commands now share PostgreSQL overlap protection and retain run outcomes.
Apply migrations before using them, then inspect recent work with:

```bash
uv run --locked python manage.py migrate
uv run --locked python manage.py loader_status --limit 10
```

A conflicting invocation records `skipped` and exits nonzero before NHL requests.
Run/progress events appear on stderr and in the application log. Logs now use
UTC JSON records with task/run correlation and failure tracebacks. Server services
can use `NHL_LOG_DESTINATION=console` for journald; local file logs require host
rotation. See [logging and retention](docs/celery-operations.md#logging-and-retention) and
[overlap protection and run history](docs/loader-runs.md) for failure recovery,
transaction requirements and the new tracking-table migration.

The scoreboard and game pages automatically check saved data every minute while
visible. **Data saved** and **Last checked** distinguish loader publication from
browser polling; stale unfinished games and unavailable supplementary stats are
labelled. Pause automatic checks or use **Refresh now** as needed. These checks
do not run loaders. See [browser freshness](docs/celery-operations.md#browser-refresh-and-freshness).

Inspect saved scheduler health without starting work:

```bash
uv run --locked python manage.py scheduler_health
uv run --locked python manage.py scheduler_health --json
```

See [scheduler health](docs/scheduler-health.md) for exit codes, thresholds and
limits. Disabled scheduling returns exit code 2; live service availability is
not probed.

## Run Development Server

```bash
uv run --locked python manage.py runserver
```

Use Python's `breakpoint()` or pytest's `--pdb` for debugging. The obsolete
`django-pdb` integration was removed because its middleware crashes on Django 5.2.

Open: `http://127.0.0.1:8000/`

The Players and team detail pages have season selectors. Their default is the
latest season loaded into SBS; players with only older data are excluded from a
newer selection. Players tables show overall season statistics, while team tables
show each player's contribution to that team. See
[Players table behavior and tests](docs/players-season-table.md) and
[team table behavior and tests](docs/team-season-tables.md).

Favorites and comparison also have season selectors. Saved players without data
for that season remain visible with dashes; career comparison modes are independent
of the season, and Favorites gamelog covers all stored seasons. See the
[saved-list behavior and complete update workflow](docs/saved-player-season-tables.md).

## Tests

Use the locked Python 3.12 environment and a PostgreSQL role dedicated to tests.
See [test environment setup](docs/testing.md) before the first database test run.

```bash
make test
make test-cov
make test-ci
```

The current offline suite passes **1042 tests at 91.68% combined line/branch
coverage**, retaining the initial 35% gate. The GitHub Actions workflow runs that
gate against isolated PostgreSQL. See the [baseline and CI details](docs/coverage-baseline.md).

Twenty-six optional Chromium smoke checks run separately with `make test-browser` after
[browser setup](docs/browser-smoke-tests.md). Default tests and local hooks exclude
browser checks; CI is configured to run both suites.

Run the optional read-only live NHL contracts explicitly:

```bash
make test-external
```

These paced checks use a completed reference season/game, never load application
data, and stop on the first failure. They remain outside normal tests, hooks and
CI. See [live check scope and failure handling](docs/live-api-checks.md).
