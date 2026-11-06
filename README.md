# NHL Web App

NHL web app for tracking player stats, game data, favorites, and player comparisons.

The [modernization roadmap](docs/modernization-roadmap.md) records completed work,
remaining test gaps, and the planned Python/Django upgrade sequence.

## Stack

- Python 3.12.16
- Django 5.2.18 LTS
- PostgreSQL 14+ (validated with PostgreSQL 16)

Django 5.2 is the planned LTS endpoint of the staged upgrade. See
[upgrade progress and validation](docs/django-upgrade-checkpoints.md).

## Local Setup

From the project root:

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-bootstrap.txt
pip install -r requirements.txt
```

If you use pyenv, this repo includes `.python-version` pinned to `3.12.16`.
When changing Python versions, recreate the venv; follow the
[Python bridge instructions](docs/django-upgrade-checkpoints.md#checkpoint-5-python-31022-to-31216).

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
python -m pip install -r requirements-hooks.txt
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
`python -c 'import secrets; print(secrets.token_urlsafe(50))'`.
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

## Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

## Populate NHL Data

From the project root, with your venv activated, run the daily sequence with:

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

To select the interpreter without activating your venv:

```bash
make update-daily PYTHON=venv/bin/python
```

Run update commands in this order for regular updates:

```bash
python manage.py upd_tms
python manage.py upd_pls
python manage.py upd_pls_tot --mode=current
python manage.py upd_gms
```

`upd_pls` updates player metadata, ordinary statistics columns, and the current
season's `sbs_stats` / `sbs_stats_avg` rows together. It can add a new season without
a full historical refresh. Reports are fetched and validated before the database
update; a failed report leaves the previous statistics intact. Players absent
from the season's reports keep their historical data.

Run a full player totals rebuild only when needed:

```bash
python manage.py upd_pls_tot --mode=full
```

Current mode also creates or refreshes season rows directly from NHL reports,
without player landing calls. Full mode refreshes profile/career data from landing
responses and season statistics from reports, including separate team contributions
for traded players. See [season loader behavior and tests](docs/season-statistics-loaders.md).

Optional projection update:

```bash
python manage.py upd_pls_proj
```

For game-response failures and safe reruns, see [game-loader behavior](docs/game-loading.md).
Supported loader GETs use bounded retries with `Retry-After` cooldowns; persistent rate
limits stop the sequence. See [shared HTTP policy and reruns](docs/loader-http.md).

## Update Cadence

- `upd_tms`: run weekly to keep team metadata current.
- `upd_pls`, `upd_gms`: run frequently (for example daily).
- `upd_pls_tot --mode=current`: run frequently to refresh current-season and career aggregates without heavy landing calls.
- `upd_pls_tot --mode=full`: run occasionally for historical refresh/backfill.

## Run Development Server

```bash
python manage.py runserver
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

Use the active Python 3.12 environment and a PostgreSQL role dedicated to tests.
See [test environment setup](docs/testing.md) before the first database test run.

```bash
make test
make test-cov
make test-ci
```

The current offline suite passes **893 tests at 90.86% combined line/branch
coverage**, retaining the initial 35% gate. The GitHub Actions workflow runs that
gate against isolated PostgreSQL. See the [baseline and CI details](docs/coverage-baseline.md).

Twenty-one optional Chromium smoke checks run separately with `make test-browser` after
[browser setup](docs/browser-smoke-tests.md). Default tests and local hooks exclude
browser checks; CI is configured to run both suites.

Run live external API tests explicitly (for example in nightly jobs):

```bash
python -m pytest -c players/tests/pytest.ini -m external players/tests/integration
```
