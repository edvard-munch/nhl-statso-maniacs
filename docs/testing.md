# Running deterministic tests

Run commands from the repository root. The supported baseline is Python 3.12.16,
Django 5.2.18 and PostgreSQL 14+ (validated on 16). The
[uv workflow](uv-migration.md) describes dependency maintenance and the migration
from pip. Hosted CI and deployment verification remain separate operational checks.

## Python environment

Install uv (CI pins 0.10.10), then create the locked environment:

```bash
uv python install 3.12.16
uv sync --locked
uv run --locked python --version
uv run --locked python -m django --version
uv pip check
make lock-check requirements-check
```

The default `dev` group includes tests, hooks and lint tools. uv manages `.venv/`;
activation is optional. Existing `venv/` and `VIRTUAL_ENV` do not select the test
interpreter. For isolated validation, set `UV_PROJECT_ENVIRONMENT` to a dedicated
absolute path; relative values are resolved from the project root. Do not point
it at a shared or system Python environment, because sync removes extra packages.
Restart app/worker processes after switching environments.

`pyproject.toml` and `uv.lock` replace hand-maintained requirements. The remaining
`requirements.txt` is generated from the lockfile; `make requirements` regenerates
it and `make requirements-check` detects drift. The old bootstrap and hook files
are retired. Security checkpoints and prior pip validation are recorded in
[coverage history](coverage-baseline.md); the current locked suite retains the 35%
coverage gate. Exact sync removes unused packages from the selected uv environment;
the old `venv/` is untouched and is no longer used by project commands.

Configure `.env` as described in the README. Normal settings require database,
allowed-host and email values even when tests do not use the application database.
Never commit real secrets. The test-specific overrides below take precedence.

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

Run this block from the repository root. Enter the password
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
uv run --locked python -m pytest -c players/tests/pytest.ini \
  players/tests/unit/other/tests_requests_mock.py

# Isolated legacy view/lookup tests and utilities
uv run --locked python -m pytest -c players/tests/pytest.ini \
  players/tests/unit/tests_readonly_db \
  players/tests/unit/other/tests_utils.py

# Collection without executing test bodies
uv run --locked python -m pytest -c players/tests/pytest.ini players/tests --collect-only

# Coverage baseline and the agreed initial 35% gate
make test-cov
make test-ci
```

All test Make targets call `uv run --locked python -m pytest` in the project
environment. A stale lockfile blocks the run instead of silently resolving it.
The current targets select `players/tests`; include `users` deliberately when
adding user-app tests. Unit/integration markers describe test boundaries; the
legacy `unit/tests_readonly_db` folder now contains marked integration tests.

Default selection excludes tests marked `external` or `browser`. Requests in deterministic
loader tests are mocked, and view/lookup tests explicitly block live HTTP.
Optional live tests can be collected separately without contacting NHL:

```bash
uv run --locked python -m pytest -c players/tests/pytest.ini -m external \
  players/tests/integration --collect-only
```

Run the live suite with `make test-external`. These read-only, paced contracts
cover supported loader sources using a completed season/game, with no database
fixtures or publication commands. They are not added to normal CI or hooks.
See [scope and failure handling](live-api-checks.md). Collection alone does not
establish live availability; HTTP outages and schema drift fail the live run.

## Local commit and push hooks

Sync the locked hook tool and ensure uv is on PATH (including in Git GUIs):

```bash
uv sync --locked
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
uv run --locked python scripts/run_hook_tests.py
uv run --locked python scripts/run_hook_tests.py --coverage
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
uv run --locked python -m pre_commit run offline-tests --all-files --hook-stage commit
uv run --locked python -m pre_commit run offline-coverage --all-files --hook-stage push
```

The `commit`/`push` stage names match pre-commit 2.21. Local test hooks use
`language: system` with `uv run --locked`; the standard-library runner also invokes
uv directly for pytest. No Python command needs to be on PATH, and a legacy venv
cannot override the locked interpreter. Missing uv, stale lockfiles, sync failures
or missing test credentials block the hook without fallback. Ruff keeps its pinned
managed hook environment. Git needs access to uv, PostgreSQL and the test config.
Run `make hooks` again after this migration so installed launchers use `.venv/`.

Hooks can be bypassed locally; GitHub CI is the independent check of pushed code.
A push can contain several commits and CI checks its latest snapshot. Required
status checks/branch protection must be configured separately to block merging
when CI fails; this change does not modify repository settings.

## Validation status

The initial [measured baseline](coverage-baseline.md) was 74.65% combined line/branch
coverage, and both coverage targets pass the unchanged 35% gate with 336 tests.
That historical gate also passed in a fresh Python 3.7.17 environment. After adding hook-runner
regression tests, both hook stages pass all 349 offline tests, with the same 74.65%
coverage and 12 external checks deselected. `.coverage` and `coverage.xml` are
generated and ignored by Git. Both stages also passed with no `python` command on PATH. Hook validation used a disposable PostgreSQL cluster
and temporary credential file; no application database or real commit/push was used.

The workflow in `.github/workflows/tests.yml` runs on pushes, pull requests and
manual dispatch. It installs pinned uv and runs `uv sync --locked` on Python
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


Shared table-rendering regressions live in
`players/tests/unit/other/tests_table_rendering.py` and
`players/tests/integration/tests_table_rendering_db.py`. They check literal names
and tooltip text containing HTML characters, balanced links/cells, numeric
precision, zero versus missing values and real AJAX responses without changing
stored records. They run in the normal offline suite; the existing Chromium suite
also validates the corrected markup in the actual tablesorter UI.

Checkbox rendering has separate unit and AJAX regressions in
`tests_checkbox_rendering.py` and `tests_checkbox_rendering_db.py`. These protect
literal labels, tooltip text, quoted attributes, checked/empty selections and
eight-option wrapping. Team, country and position values are decoded from rendered
HTML and sent back through real totals/averages filter requests; selecting and
clearing them must preserve values and leave stored players/teams unchanged.

`tests_upd_gms_malformed_rosters_db.py` protects malformed roster rejection on new
and existing days, complete rollback when a later game fails, and repaired replay.
It reuses the existing synthetic game/report fixture, snapshots saved player/game
data and relationships, and preserves unavailable-roster and nested-format behavior.
See [game-loading contracts](game-loading.md#malformed-supplied-rosters).

`tests_upd_gms_changed_participants_db.py` covers removed/replaced participants in
all six roster groups, bench-goalie corrections, position/side changes, game-ID and
legacy cleanup safeguards, shared skater/goalie database IDs, repeat loads and
rollback after cleanup. Ambiguous legacy entries are retained with a warning;
older history, unrelated players and saved memberships remain protected.

`tests_nhl_http.py` checks shared retry budgets, numeric/date `Retry-After`, bounded
backoff, permanent HTTP failures and loader-entry integration. Offline fixtures
replace sleeps; explicitly marked external API tests retain real cooldown waits.
Career and team persistence regressions cover exhausted rate limits, unchanged
current-player data, optional fallbacks and retried image downloads. See the
[shared loader HTTP policy](loader-http.md).

## Optional browser smoke tests

Twenty-two Chromium cases exercise Players, authenticated saved-list controls,
favorites removal with filters/pagination, empty transitions, team layouts and
AJAX failure/retry recovery against the isolated live server. See
[browser setup and CI](browser-smoke-tests.md) before `make test-browser`. Browser
checks are separate from the offline coverage gate and local commit/push hooks;
CI runs both. The current offline result is 942 passed, 22 external and 22 browser
cases deselected, at 91.30% combined coverage. Saved-list mutations are POST-only,
with CSRF rejection and persistence checks in the offline suite and real CSRF
headers checked in Chromium. See [saved-list requests](saved-player-season-tables.md#saved-list-requests).

`TestConcurrentSavedActions` runs 23 PostgreSQL transaction cases. Separate
authenticated clients use independent thread-local connections; events hold the
first request's account lock while `pg_blocking_pids` verifies the second request
is waiting on it. These protect shared favorites capacity, per-type comparison
capacity, repeated toggles, removal/addition, both reset/toggle orders and
independent accounts. Rendering-failure cases check rollback and subsequent use.
No sleep is used as proof of locking: polling observes PostgreSQL's actual lock
wait, with bounded waits and closed worker connections. These cases are part of
the ordinary offline suite and CI; no browser or live NHL access is required.
