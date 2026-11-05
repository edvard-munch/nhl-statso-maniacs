# Running deterministic tests

Run commands from the repository root. The current baseline is Python 3.12.16,
Django 5.2.18 and PostgreSQL 14+ (validated on 16). The planned LTS endpoint is
validated locally; hosted CI, deployment checks and uv follow separately, as
recorded in the roadmap.

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
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-bootstrap.txt
python -m pip install -r requirements.txt
python -m pip check
```

The requirements pin the Django 5.2.18 checkpoint and compatible extensions.
The target Python 3.12.16 environment passes `pip check`, Ruff and all 724 offline
tests with the 35% coverage gate (90.13% combined coverage). The bootstrap file
pins packaging tools, including setuptools compatible with Python 3.12. This
validates the current install
procedure, not a full transitive lockfile; uv remains separate work.

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

## Local commit and push hooks

Install the pinned hook tool in the project venv:

```bash
source venv/bin/activate
python -m pip install -r requirements-hooks.txt
```

Use the dedicated PostgreSQL role/database created above. Copy the example once:

```bash
cp test-database.example.json test-database.local.json
```

Edit `test-database.local.json` to use that role's password. All values, including
the port, are JSON strings. The file is ignored by Git and is the only credential
source for hook tests. The default database name `nhl_test_base` produces the
migrated test database `test_nhl_test_base`. The role must be able to create/drop
that test database. A name beginning with `nhl_test_` is required for the base
configuration; do not use application data or credentials.

The runner also accepts an alternate config path through
`NHL_TEST_DATABASE_CONFIG`, useful for disposable validation environments.
Missing/invalid config stops the hook; it does not use `POSTGRES_*` from the
application shell. Host and port support separate local PostgreSQL installations.
The runner uses normal application settings with explicit test database overrides,
local-only email and test-only Django environment values. Inherited pytest flags
are cleared so `--lf`, live-test selection or migration bypasses cannot silently
narrow the intended run.

Check the setup before installing hooks:

```bash
python scripts/run_hook_tests.py
python scripts/run_hook_tests.py --coverage
make hooks
```

`make hooks` installs both `pre-commit` and `pre-push` hooks. Installation is local
to each clone; committing the config does not install hooks on other machines.

| Event | Checks |
| --- | --- |
| Commit | Ruff formatting/lint on relevant changed files, followed by the complete offline test suite. |
| Push | Ruff lint on relevant changed files, followed by the complete offline suite and the 35% coverage gate. |
| GitHub push/PR | Independent clean-environment lint, JavaScript checks and coverage gate using disposable PostgreSQL. |

The test hooks always run, including for documentation-only commits, and receive
no changed-file arguments: a changed-file list never substitutes for the full
suite. Failures block the commit/push. Ruff may reformat files during a commit;
review and stage those changes before retrying. Checks are serial within each
hook invocation. Optional live API tests remain excluded.

To run hooks manually:

```bash
make hooks-run
make hooks-run-push
```

These all-file commands also check existing files outside the current change;
`hooks-run` can format them. To run only a test hook during troubleshooting:

```bash
python -m pre_commit run offline-tests --all-files --hook-stage commit
python -m pre_commit run offline-coverage --all-files --hook-stage push
```

The `commit`/`push` stage names match the pinned pre-commit 2.21 tool; upgrading
that tool belongs with the Python transition. Pre-commit supplies a managed Python to launch the standard-library runner,
so a GUI does not need `python` on PATH. The runner uses the repository's
`venv`/`.venv` before any active environment; the managed hook environment does
not need Django installed. Git still needs access to the local PostgreSQL server
and config file. The first run initializes the managed hook environment.

Hooks can be bypassed locally; GitHub CI is the independent check of pushed code.
A push can contain several commits and CI checks its latest snapshot. Required
status checks/branch protection must be configured separately to block merging
when CI fails; this change does not modify repository settings.

## Validation status

The [measured baseline](coverage-baseline.md) is 74.65% combined line/branch
coverage, and both coverage targets pass the unchanged 35% gate with 336 tests.
The same gate passes in a fresh Python 3.7.17 environment. After adding hook-runner
regression tests, both hook stages pass all 349 offline tests, with the same 74.65%
coverage and 12 external checks deselected. `.coverage` and `coverage.xml` are
generated and ignored by Git. Both stages also passed with no `python` command on PATH. Hook validation used a disposable PostgreSQL cluster
and temporary credential file; no application database or real commit/push was used.

The workflow in `.github/workflows/tests.yml` runs on pushes, pull requests and
manual dispatch. It installs the bootstrap tools and requirements on Python
3.12.16 / Ubuntu 22.04, checks dependencies and lint/JavaScript syntax, then runs
`make test-ci` with a PostgreSQL 16 service and real test migrations. Its disposable
database credentials come from the workflow, without application secrets or `.env`.
It uploads the XML coverage report, including when tests fail if data was produced.
The hosted run on `b55ab9d` failed before tests because a clean checkout lacked
`logs/`. Settings now create that directory before configuring file logging;
a new regression reproduces startup with no existing runtime directories. A clean
temporary checkout passed 408 tests and the 82.59% gate and exported XML locally.
Coverage export/upload run only when their input files exist. The fixed workflow
still needs a new hosted run after push.
