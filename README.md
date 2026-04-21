# NHL Web App

NHL web app for tracking player stats, game data, favorites, and player comparisons.

## Stack

- Python 3.7.17
- Django 2.2.6
- PostgreSQL

## Local Setup

From the project root:

```bash
python3.7 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you use pyenv, this repo includes `.python-version` pinned to `3.7.17`.

## Code Quality

This project uses Ruff for formatting and linting.

```bash
make format
make lint
make check
```

Optional pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Pre-commit uses Ruff's official hook configuration, so it does not depend on a GUI app resolving your local `python` executable.


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

Run a full player totals rebuild only when needed:

```bash
python manage.py upd_pls_tot --mode=full
```

Optional projection update:

```bash
python manage.py upd_pls_proj
```

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

## Tests

```bash
make test
make test-cov
make test-ci
```

Run live external API tests explicitly (for example in nightly jobs):

```bash
pytest -c players/tests/pytest.ini -m external players/tests/integration
```
