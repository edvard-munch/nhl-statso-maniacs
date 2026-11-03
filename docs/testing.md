# Running deterministic tests

Run commands from the repository root. The current baseline is Python 3.7.17,
Django 2.2.6 and PostgreSQL. Keep this stack while establishing the baseline;
Python/Django and uv changes are later, separate roadmap stages.

## Python environment

Use `venv` as the documented environment directory. If the working environment
already exists under `.venv`, activate that instead; there is no need to recreate
it just to change its name.

```bash
source venv/bin/activate
python --version
python -m django --version
python -m pip check
```

For an environment that does not yet exist:

```bash
python3.7 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

The requirements remain the existing pinned legacy set. The current installed
venv passed `pip check`; a clean install of every pin has not yet been verified.
Record installation failures rather than upgrading unrelated dependencies to
make a test run work. Clean-environment verification remains a roadmap task.

Configure the project's `.env` as described in the README. Django loads the normal
application settings, which require database, allowed-host and email values even
when tests do not use email or the application database. Never commit real secrets.
The test-specific database overrides below take precedence over `.env` values.

## PostgreSQL test role and databases

Use a dedicated local PostgreSQL role rather than an application or production
role. On a local installation managed by the `postgres` OS user, an administrator
can run these commands once:

```bash
sudo -u postgres createuser --createdb --pwprompt nhl_test_runner
sudo -u postgres createdb --owner=nhl_test_runner nhl_test_base
```

Skip creation if those objects already exist. The role needs permission to create
and drop its test database, not superuser privileges. The configured base database
is `nhl_test_base`; pytest-django creates and migrates `test_nhl_test_base`, runs
the tests there, and drops it afterward. Keep both databases dedicated to tests.
Default application settings use PostgreSQL at localhost:5432.

Activate the venv and run this block from the repository root. Enter the password
you chose when creating the test role:

```bash
(
  export POSTGRES_DB=nhl_test_base
  export POSTGRES_USER=nhl_test_runner
  read -r -s -p 'Test database password: ' nhl_test_password
  echo
  export POSTGRES_DB_PASSWORD="$nhl_test_password"
  make test
)
```

The subshell keeps these overrides out of the surrounding application shell.
No update commands or application migrations are part of this test run. Test
records are created through function-scoped fixtures; no developer account,
existing NHL records or legacy database dumps are required.

Use real migrations. Do not add `--nomigrations`: legacy ImageField model/schema
mismatches make the model-generated schema unsuitable for that shortcut. If
PostgreSQL is unavailable or role creation is denied, fix the test database setup;
do not restore the removed database-setup bypass or unblock application data.

## Commands and selection

Within the same test-only subshell, replace `make test` as needed:

```bash
# Default offline suite
make test

# Focused request tests, which do not need database access
python -m pytest -c players/tests/pytest.ini \
  players/tests/unit/other/tests_requests_mock.py

# Isolated legacy view/lookup tests and utilities
python -m pytest -c players/tests/pytest.ini \
  players/tests/unit/tests_readonly_db \
  players/tests/unit/other/tests_utils.py

# Collection without executing test bodies
python -m pytest -c players/tests/pytest.ini players/tests --collect-only

# Coverage baseline and the agreed initial 35% gate
make test-cov
make test-ci
```

All test Make targets call `python -m pytest` through the activated interpreter.
The current targets select `players/tests`; include `users` deliberately when
adding user-app tests. Unit/integration markers describe test boundaries; the
legacy `unit/tests_readonly_db` folder now contains marked integration tests.

Default selection excludes tests marked `external`. Requests in deterministic
loader tests are mocked, and view/lookup tests explicitly block live HTTP.
Optional live tests can be collected separately without contacting NHL:

```bash
python -m pytest -c players/tests/pytest.ini -m external \
  players/tests/integration --collect-only
```

Actual live checks require dropping `--collect-only`. Some still describe retired
API contracts and need the deferred maintenance in the roadmap; collecting them
does not establish that they pass against NHL today.

## Validation status

Update the [roadmap](modernization-roadmap.md) with the latest full-suite result.
A normal passing run does not measure coverage. Run both coverage targets before
claiming the 35% gate passes; `.coverage` artifacts are generated and ignored by
Git. CI and a verified fresh installation remain separate follow-up work.
