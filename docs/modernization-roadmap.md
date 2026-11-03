# Regression testing and modernization roadmap

Reviewed: 2026-11-03. This records the work agreed in this chat and the remaining
sequence. Update the status and evidence as each small commit lands.

## Goal and recommendation

Upgrade the app from Python 3.7 / Django 2.2 to a supported stack while preserving
loader correctness, historical data and user-facing behavior. Make one focused
change at a time and validate before moving to the next stage.

**Next: stabilize the complete offline test suite and measure coverage.** The
season-statistics work is complete enough to move on. Add tests for the remaining
high-risk behavior after collection and database isolation are reliable. Do not
wait for 100% coverage before starting the upgrade.

## What is already complete

| Area | Completed work |
| --- | --- |
| Update documentation | Weekly team updates; frequent player/game/current totals updates; occasional full historical backfill. |
| Test infrastructure | pytest-cov, line/branch coverage for `players`, unit/integration/external markers, external deselection, Make targets and an initial 35% gate. |
| Coverage artifacts | `.coverage` and `.coverage.*` excluded from Git; generated files are disposable. |
| Loader helpers | Mocked team/player helpers, numeric fields, countries/logging, time formatting and season detection/fallback. |
| Incomplete career data | Average calculations hardened; focused regression tests added. |
| Season contracts | Synthetic old/current/traded/goalie/missing-data fixtures and parser/reader contracts. |
| Shared reader | Canonical season selection, totals and derived averages, team splits, combined rows, zero/unknown statistics. |
| Season loaders | `upd_pls` and totals modes maintain SBS rows; mocked persistence, repeat runs, precedence and rollback contracts. |
| Players table | Reads selected-season SBS statistics before filtering/sorting/pagination; avoids stale snapshot fallback. |
| Team tables/AJAX | Read the selected team's season contribution, independently of current roster links. |
| Favorites/comparison | Selected-season projections; saved identities retained without season data; career modes separate; AJAX selection retained. |
| NHL split-label fix | Accept combined `teamAbbrevs` on team-filtered numbers while reconciling split counts; regression coverage for Nico Daws's response shape. |

The implementation commits are present through `040b674` (NHL split labels),
following `f0d5729` (saved lists). Detailed contracts live in
[fixtures](season-statistics-fixtures.md), [reader](season-statistics-reader.md),
[loaders](season-statistics-loaders.md), [Players](players-season-table.md),
[teams](team-season-tables.md) and [saved lists/workflow](saved-player-season-tables.md).

## Evidence and limits

- The latest complete default run passed **336 tests**, with **12 external tests
  deselected**, against a disposable PostgreSQL cluster with real migrations.
  The previously failing request mocks now freeze the season and compare semantic
  query values, including pagination and timeout. Ruff checks passed; the current
  installed venv also passed `pip check`. Coverage is not measured by this run.
- The repaired split fetch was validated read-only against the live API: combined
  6 games / 117 saves, NJD 4 / 75, WPG 2 / 42. This was not a full loader run.
- Favorites JavaScript had syntax and lightweight controller smoke checks;
  comparison JavaScript had syntax checks. Browser interaction coverage remains
  to be added.
- The application's database was not modified by these validation runs. A complete
  successful local update after the latest fix has not been reported in the chat.
- **Collection and database isolation are repaired.** The original collection
  repair selected 320 default tests; after replacing and expanding legacy/request
  tests, the default suite selects 336 tests and deselects 12 external tests.
  Removed-command imports and obsolete helper references are gone. HTTP requests
  and database connections were explicitly blocked for the earlier collection
  checks; normal execution now uses pytest-django's migrated test database.
- Legacy view/lookup tests now create per-test synthetic users, teams, players,
  games, sides and saved lists. Live HTTP is blocked in that test directory.
  Utility tests no longer load database dumps at session scope. The legacy
  `tests_readonly_db` folder name remains for compatibility; its database tests
  are marked integration tests.
- The complete coverage baseline is **not established**. The 35% gate was an
  agreed starting threshold, not a measured result or a reason to exclude code.
- The current Make targets select `players/tests`; tests added under `users`
  must be included deliberately in the normal run and CI.

## 1. Make the normal test run reliable

Suggested focused commits, in order:

1. **Completed: repair collection and separate optional live checks.** Removed
   the obsolete SBS command import and replaced the obsolete totals helper with
   a landing-response check. Both selections collect without HTTP/database access.
   Remaining legacy live API contracts still need the deferred maintenance below.
2. **Completed: replace legacy database-dependent tests with isolated fixtures.**
   Removed the `django_db_setup` bypass and database-unblocking fixture. Replaced
   local-account login and existing NHL records with per-test synthetic fixtures,
   explicit authentication and relationship assertions. Anonymous private endpoints
   now assert their actual 403 contract; anonymous player actions assert no writes.
   Replaced session-wide utility database dumps with function-scoped records and
   fixed the measurements test to check both height and weight.
3. **Completed: repair stale request mocks.** Tests freeze two explicit seasons,
   isolate mutable request parameters and assert semantic query values rather than
   URL whitespace/order. Success, pagination, timeout configuration and the HTTP
   401 response contract remain checked without live requests.
4. **Documented; fresh-install verification remains.** The [test setup guide](testing.md)
   standardizes `venv`, describes the required application `.env` and a dedicated
   PostgreSQL role/database, and scopes test credentials to a subshell. Make test
   targets now use `python -m pytest` through the activated interpreter. Real
   migrations remain required. Verify a fresh installation from declared
   dependencies separately; the populated venv and its passing `pip check` do not
   prove that every pin can be reinstalled.
5. **Measure the baseline and run the gate.** Run `make test`, `make test-cov`, and
   `make test-ci`; record test counts, line/branch coverage and gate outcome. If
   below 35%, cover meaningful gaps without weakening the agreed threshold.
6. **Add CI for the same offline suite.** Supply an isolated PostgreSQL service,
   migration setup, normal tests, the coverage gate and relevant static checks.
   Optional external checks belong in a separate explicit job.

Done when a fresh test database and documented environment can run the default
suite repeatedly, with no application-data dependency, and coverage is measured.
The legacy database bypass is now removed; the full run has been verified against
an explicitly isolated PostgreSQL configuration. Continue to use an isolated test
database and real migrations; never point tests at application data.

## 2. Close the highest-risk regression gaps

Extend the existing fixtures/parsers instead of duplicating them. Treat each row
below as a small batch, splitting implementation fixes from unrelated cleanup.

| Priority | Work | Behavior to protect |
| --- | --- | --- |
| First | `upd_gms` response handling | Reproduce the reported JSONDecodeError with empty/HTML/non-200 responses; add timeout/status/JSON handling and bounded retries with game/date context. Decide which unavailable future games can be deferred, and ensure replay is safe. `get_game_data()` still calls `.json()` directly. |
| First | Loader orchestration | Audit remaining `upd_pls.import_player` branches, report pagination/coverage, failure-before-publication, absent players, season detection and current/full totals precedence. Much is covered already; use coverage to find real gaps. |
| First | Game persistence | Mocked schedule/boxscore/report inputs, repeated loads, missing players, saved game values and failure boundaries. Preserve existing report parser tests. |
| Next | Team persistence | Complement mocked `upd_tms` ORM calls with real isolated saves and repeat runs. |
| Next | User-facing views | Player detail/career tables, search/filtering, games/detail/date navigation, 404s and empty/invalid inputs. Reuse existing season-table tests. |
| Next | Auth and user-owned actions | Login/registration/profile, favorite/comparison add/remove/limits/privacy, notes/positions and measurements. Audit existing saved-list coverage before adding cases. |
| Next | Model/util/template logic | Cover substantive rules and escaping/formatting contracts rather than tests that duplicate implementation. |
| Next | Browser smoke tests | Actual season selection, favorites goalie-only/empty lists, totals/averages, comparison modes/removal/reset and team joined/split controls; assert displayed values and AJAX season persistence. |

The reported `upd_gms` JSON failure was investigated but is not fixed by the NHL
split-label change. Bring that issue forward if it still blocks normal updates.
Player-detail season selection is also a separate product change; characterize
its current behavior first, then decide whether to extend the selector there.

Done when the important loader failure paths and user workflows have regression
checks that would catch a framework upgrade breaking them. Coverage guides this
work; test count alone does not establish readiness.

## 3. Make updates convenient and confirm the data workflow

The documented sequence remains:

```bash
python manage.py upd_tms &&
python manage.py upd_pls &&
python manage.py upd_pls_tot --mode=current &&
python manage.py upd_gms
```

`&&` stops at the first failing command. For daily updates omit `upd_tms` when
team metadata is already current; run it weekly. Full totals mode remains an
explicit occasional refresh/backfill, not part of the daily sequence.

A follow-up convenience commit can add `make update-daily` and `make update-all`
with this fail-fast ordering. These targets are **not implemented yet**. Keep full
historical refresh explicit. Do not add scheduling until manual runs are reliable.
After a successful refresh verify the new season on Players, teams and saved
lists; absence of a season row must not display an older snapshot as current.

## 4. Reproduce dependencies and choose the uv transition

`pyproject.toml` currently holds Ruff configuration, not project dependency
metadata; there is no uv lockfile. Before changing tools, capture the working
interpreter/dependency set and identify obsolete or incompatible packages.
Review Django integrations, Celery/results, storage, PostgreSQL driver, Pillow,
pytest/pytest-django/coverage, documentation tools and production entry points.

Correction to the earlier chat advice: current uv documentation lists Python
3.7 as Tier 2, rather than universally excluding it. That does **not** prove this
project's dependency resolution, `uv sync`, or interpreter provisioning will work.
Validate the exact uv version and workflow in a fresh environment before changing
the standard setup. See [uv Python support](https://docs.astral.sh/uv/reference/policies/python/).

Suggested sequence: stabilize the baseline; reach Django 3.2; establish a compatible
Python bridge; introduce `[project]` metadata, explicit Python constraints and
runtime/test/dev dependencies; generate `uv.lock`; verify clean sync and tests;
then update Make targets, CI and documentation together. A successful isolated
uv trial can justify moving it earlier. Keep tool migration and framework upgrades
in separate commits, preserving a working setup until the replacement is proven.

## 5. Upgrade Django and Python in controlled stages

Retain the agreed checkpoints **2.2 → 3.2 → 4.2 → 5.2**. Read release notes and
resolve deprecations across intervening feature releases; use smaller steps if
needed. The older releases are temporary upgrade checkpoints, not deployment
targets. Django 4.2 support ended in April 2026; Django 5.2 is the intended LTS
endpoint. See the [5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/).

| Checkpoint | Proposed interpreter strategy | Main work |
| --- | --- | --- |
| Existing 2.2.6 | Keep Python 3.7 initially | Establish baseline; update to the final 2.2 patch in a separate checked change. |
| Django 3.2 | Keep 3.7 for the framework change, then test 3.10 separately | Upgrade compatible dependencies; remove deprecations; prepare JSONField/schema changes. Python 3.10 is only a bridge. |
| Django 4.2 | Keep 3.10 for the framework change, then test 3.12 separately | Replace removed APIs, resolve migration/JSONField/storage/time-zone issues and dependency constraints. |
| Django 5.2 | Use the validated Python 3.12 environment | Complete removals/deprecations, verify deployment and record the supported final dependency set. |

The bridge choices follow the official compatibility ranges in the
[3.2](https://docs.djangoproject.com/en/3.2/releases/3.2/),
[4.2](https://docs.djangoproject.com/en/4.2/releases/4.2/) and
[5.2](https://docs.djangoproject.com/en/5.2/releases/5.2/) notes. They are proposals,
not tested project configurations. Keep interpreter changes separate from Django
changes wherever possible.

At every checkpoint:

- Recreate the environment and run the offline tests and coverage gate.
- Run Django system checks, migration consistency checks and migration plans.
  Test both a fresh database and migration of a disposable copy of existing data.
- Run mocked loader persistence/smoke tests and the critical browser flows.
- Review deprecation warnings and resolve the ones affecting the next checkpoint.
- Check static/media/profile images, login/session behavior and deployment jobs.
- Review schema compatibility explicitly: PostgreSQL-specific ArrayField remains,
  legacy `django.contrib.postgres.fields.JSONField` needs migration planning, and
  ImageField model/migration mismatches must not be papered over.
- Record results and commit a working checkpoint before proceeding.

Deployment needs a tested backup/restore path and migration rehearsal on a copy.
Avoid mixing destructive data cleanup with framework/schema transitions.

## 6. Deferred maintenance

Repair optional live API tests against the new command paths and response
contracts; do not assert key order or unstable player counts unnecessarily.
Run them separately after deterministic equivalents exist. Audit unused scripts
and dependencies by checking callers, docs and scheduled jobs before removal.
Only then consider removing obsolete snapshot/cache fields or replacing SBS JSON
with relational season rows; neither is required for the current fix or upgrade.

## Immediate commit queue

1. Completed: fix test collection without importing removed commands.
2. Completed: replace database bypass and existing-record tests with isolated fixtures.
3. Completed: repair season-sensitive mocks and document the test environment.
4. Record full-suite coverage and wire the verified suite into CI.
5. Harden game JSON fetching with regression tests for the reported failure.
6. Add remaining high-value loader/user-flow tests, then begin the staged upgrade.

Use small focused commits with messages explaining both what changed and why.
The next implementation task is item 4: measure full-suite coverage and the 35%
gate, record the baseline, then wire the verified workflow into CI. A fresh install
from requirements still needs verification before claiming dependency reproducibility.
