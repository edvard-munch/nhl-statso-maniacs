# NHL Web App

NHL web app for tracking player stats, game data, favorites, and player comparisons.

The [modernization roadmap](docs/modernization-roadmap.md) records completed work,
remaining test gaps, and the planned Python/Django upgrade sequence.

## Stack

- Python 3.12.16
- Django 4.2.30
- PostgreSQL

Django 4.2.30 is the current temporary upgrade checkpoint. See
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

Create a `.env` file in the project root with these keys:

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

## Update Cadence

- `upd_tms`: run weekly to keep team metadata current.
- `upd_pls`, `upd_gms`: run frequently (for example daily).
- `upd_pls_tot --mode=current`: run frequently to refresh current-season and career aggregates without heavy landing calls.
- `upd_pls_tot --mode=full`: run occasionally for historical refresh/backfill.

## Run Development Server

```bash
python manage.py runserver
```

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

The measured baseline is **74.65% combined line/branch coverage**; the initial
35% gate passes with 336 offline tests. The GitHub Actions workflow runs that same
gate against isolated PostgreSQL. See the [baseline and CI details](docs/coverage-baseline.md).

Run live external API tests explicitly (for example in nightly jobs):

```bash
python -m pytest -c players/tests/pytest.ini -m external players/tests/integration
```
