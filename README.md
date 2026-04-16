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

Run update commands in this order:

```bash
python manage.py upd_tms
python manage.py upd_pls
python manage.py upd_pls_tot
python manage.py upd_gms
```

Optional projection update:

```bash
python manage.py upd_pls_proj
```

## Run Development Server

```bash
python manage.py runserver
```

Open: `http://127.0.0.1:8000/`

## Tests

```bash
pytest players/tests
```
