# Regression testing and modernization roadmap

Reviewed: 2026-11-06. This records the work agreed in this chat and the remaining
sequence. Update the status and evidence as each small commit lands.

## Goal and recommendation

Upgrade the app from Python 3.7 / Django 2.2 to a supported stack while preserving
loader correctness, historical data and user-facing behavior. Make one focused
change at a time and validate before moving to the next stage.

**Next: push and verify hosted CI, then rehearse deployment.** Django 5.2.18 now
passes 849 offline tests on Python 3.12.16, reaching the planned LTS endpoint
locally. The final framework step includes compatible Bootstrap 4 forms, task-result
migrations, removal of broken debug middleware and timezone/storage/auth regressions.
CI reads the same interpreter pin as local pyenv. The hosted dependency graph
must be rerun to confirm the former Python 3.7 blocker is cleared.
Team persistence and paginated player publication now have database regressions. Totals ordering, history preservation and per-player failure contracts are also covered.
Player biography and flag persistence now have regression coverage as well.
Career-enrichment responses now have HTTP-backed persistence contracts.
The agreed regression-testing phase is complete locally. Remaining edge cases are
deferred follow-ups; proceed to hosted CI verification and deployment rehearsal
instead of extending this phase toward 100% coverage.

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
  installed venv also passed `pip check`. Both coverage Make targets now pass;
  the combined result is **74.65%** (76.95% lines, 68.64% branches).
- Local hook configuration now runs the full offline suite before commits and
  the coverage gate before pushes. Both stages passed through pre-commit 2.21:
  **349 tests passed, 12 external tests deselected, 74.65% coverage**. Hook runner
  tests cover missing/invalid credentials and flag isolation. Hooks use an ignored
  dedicated test-database config; installing them is a per-clone setup step.
- The game-response follow-up passes **379 tests**, with **12 external tests
  deselected** and **76.88% combined coverage** through the push-stage coverage
  hook. Empty/HTML/invalid JSON, retries and client errors have mocked coverage;
  isolated PostgreSQL tests verify failed-day rollback and idempotent scheduled
  game replays. No live NHL loader run or application database was used.
- Roster/gamelog persistence and schedule-command contracts now pass **397 tests**,
  with **12 external tests deselected** and **82.53% combined coverage**. Existing
  report parser fixtures are reused. Tests exposed two repaired completion bugs:
  live rosters were treated as final, and day completion flags could remain stale
  after an incomplete refresh. `upd_gms` combined coverage is now 93%; report
  identity edge cases and malformed inputs still need contracts.
- The report-identity follow-up passes **407 tests**, with 12 external tests
  deselected and **82.59% combined coverage**. Three initially failing collision
  contracts now keep opponents' special-team points and TOI separate. Unscoped
  ambiguous HTML fields are skipped with warnings and retain existing defaults;
  recovering those counts through team/name-aware HTML parsing remains optional
  follow-up work. Existing game data is not automatically backfilled.
- The first framework checkpoint, **Django 2.2.6 → 2.2.28**, passes 408 tests at
  82.59% combined coverage on Python 3.7.17. Both versions pass system and
  model/migration checks with no changes detected. A schema migrated under 2.2.6
  needs no new migrations under 2.2.28. The isolated validation and dependency
  update are recorded in [upgrade checkpoints](django-upgrade-checkpoints.md).
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
- The [coverage baseline](coverage-baseline.md) is established: 74.65% combined
  coverage passes the unchanged 35% initial gate. A fresh Python 3.7.17 venv
  installed the requirements with pinned bootstrap tools, passed `pip check` and
  all tests, and reproduced that gate result. This is a verified install procedure,
  not a transitive lockfile.
- CI now runs the offline gate on Python 3.7.17 / Ubuntu 22.04 with a PostgreSQL 16
  service, static checks and XML coverage upload. actionlint validation passed;
  the first hosted test run on `b55ab9d` failed during logging setup because the
  fresh checkout had no `logs/` directory. Settings now create it. A clean-checkout
  reproduction passes 408 tests at 82.59% and exports XML; the repaired hosted run
  is pending after push. See [failure details](coverage-baseline.md).
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
4. **Completed: document and validate the environment.** The [test setup guide](testing.md)
   standardizes `venv` and dedicated test credentials. Make targets use the active
   Python. The pinned bootstrap tools and full requirements were installed in a
   fresh Python 3.7.17 venv; dependency checks and the full coverage gate passed.
   Keep real migrations; uv/lockfile work remains separate.
5. **Completed: measure the baseline and run the gate.** Both coverage Make
   targets pass: 336 tests, 74.65% combined coverage, unchanged 35% threshold.
   See [measured counts and gaps](coverage-baseline.md).
6. **Implemented: CI for the same offline suite.** A PostgreSQL service and real
   test migrations support `make test-ci`; lint, JavaScript syntax and XML upload
   are included. Workflow validation and a local fresh-environment reproduction
   passed. The first hosted startup failure is repaired locally; confirm the
   corrected run after push. Optional live tests remain out of the default job.

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
| Completed | `upd_gms` response handling | Shared checked JSON requests, bounded retries, game/date/endpoint errors and per-day transaction rollback. Unavailable future-game JSON remains a controlled failure; a deferral policy is separate. See [game loading](game-loading.md). |
| Core publication, totals, metadata and career-response contracts covered | Loader orchestration | Real HTTP pagination through `upd_pls` staging/persistence/replay, bios/summary identity/count checks and malformed later-page rejection are covered. Current/full totals now protect command ordering, historical replacement/replay, latest-snapshot precedence and per-player failure preservation for skaters/goalies. Biography refreshes, nationality fallback, draft preservation and local flag attachment/recovery now have real persistence contracts. HTTP-backed career current/full precedence, empty/unavailable data, partial rows and malformed-response rejection now have persistence tests. Numeric validity, aggregate identity/completeness and whole-command rollback remain separate decisions; move to user-facing coverage next. |
| Planned phase complete locally | Game persistence | Real saved roster/gamelog values through mocked schedule/boxscore/reports, missing/bench players, identity, malformed-response rejection, history preservation, rollback and replay. Corrected participants now reconcile roster links and verified date entries, with game-ID markers, guarded legacy cleanup, typed skater/goalie identity and retention of ambiguous data. |
| Completed | Team persistence | Real command/create/update/replay saves, stable IDs/slugs/player/game links, preservation of unreported metadata/history, cached/missing logos and optional-download failure recovery. Synthetic HTTP/download inputs and temporary media; 445 tests pass at 83.20% combined coverage. |
| Core profiles, games/navigation and search covered | User-facing views | Rendered career statistics, current-panel guards, gamelogs, player/game/date errors and scoreboard navigation have contracts. Search/autocomplete now cover trimmed/literal terms, empty inputs/results, canonical links, escaped labels/encoded queries and viewer-specific controls. Existing Players filtering contracts remain; move to user-owned mutation endpoints next. |
| Core private-data/preferences and saved-action contracts covered | Auth and user-owned actions | Typed notes/positions, validated profile preferences, ownership and existing CSRF contracts are covered. Sequential favorites/comparison quota boundaries, toggles, missing-target 404s, anonymous no-writes and reset isolation now have real persistence tests. Concurrent quotas and migration of legacy GET-based toggles to POST are separate decisions. |
| Table cells and filter checkboxes covered; other substantive rules remain | Model/util/template logic | Shared player links/tooltips and filter checkboxes escape dynamic text/attributes. Unit and real AJAX regressions protect numeric precision, missing values, checkbox selection/reset, literal value round-trips and unchanged stored records. Remaining model/template rules should be chosen by behavior and risk. |
| Core Players/saved-list/team workflows and failure recovery covered | Browser smoke tests | Twenty-one Chromium cases cover season/mode/layout controls, favorites last-member/final-member removal, empty transitions, comparison removal/reset and AJAX failures with explicit retries. Season retention, team contributions, reload persistence and ownership are checked. Filtered/paginated favorites removal now protects global counts, sorting, season, valid paging and ownership for both player types. |

The reported `upd_gms` JSON failure now has controlled request handling and
rollback tests; live endpoint availability is not established by mocked checks.
Future-game deferral remains a separate policy decision; changed participants,
malformed supplied rosters and shared-sweater identity are now covered.
Player-detail season selection is also a separate product change;
characterize its current behavior before extending the selector there.

The player-publication follow-up passes 456 tests at 83.57% combined coverage.
Synthetic HTTP callbacks observe the existing database throughout report fetching;
publication happens after the requests complete. Duplicate/missing bios, conflicting
games/rows, failed or malformed later pages leave all saved players unchanged,
including goalies staged before a skater failure. Repeat loads preserve identities
and historical rows. Bios without a summary do not publish a new season marker.
This does not establish live API availability or correctness of every upstream
report shape; metadata/flag and totals-enrichment edges remain separate work.

The totals follow-up adds 16 integration cases and passes the full offline suite:
488 tests, 12 external tests deselected, 84.13% combined coverage. Real PostgreSQL
saves use shared synthetic reports; current mode avoids landing calls, full mode
replaces refreshed seasons while preserving unreturned history, and historical-only
backfills retain the newer snapshot. Failure preservation is per player; whole-command
rollback and live career-enrichment response handling are not established by this batch.

Done when the important loader failure paths and user workflows have regression
checks that would catch a framework upgrade breaking them. Coverage guides this
work; test count alone does not establish readiness.

The saved-game TOI audit now provides read-only season/date/game selection and
player-level PP/SH comparisons against current NHL sources. Its 28 integration
cases bring the full offline suite to 516 passed, 12 external tests deselected,
and 84.78% combined coverage. See [audit usage](game-loading.md). Run it against
saved application data to identify mismatches and unverified games; no such live
audit has been run by this validation. The audit-hardening follow-up adds finished-game selection, request pacing,
bounded rate-limit handling, stderr progress and resumable JSONL checkpoints;
537 offline tests now pass at 85.36% combined coverage. The user's completed read-only report covers 235 games through November 2, 2026:
224 games have 3,441 PP/SH mismatches; two fields in game 2026020100 remain
unverified. The explicit `--repair` follow-up is now implemented, with 14 additional
integration cases and a full run of 551 passed / 85.67% combined coverage. It
rechecks sources, patches only verified fields, preserves unverified/concurrent
changes, and commits per game. Mode-specific checkpoints support repair resume.
See [repair workflow](game-loading.md). Application repair has not been run by this
validation; perform targeted repair and a fresh read-only verification as an
operational step. The user's repair reports now account for all 3,441 original
mismatches (34 in the example game plus 3,407 in the season run), without conflicts
or failed repairs. The user confirmed L'Heureux was rostered with zero total TOI
and absent from some reports. A focused audit fallback now derives missing PP/SH
zeroes only from explicit valid zero total TOI; nine new cases bring validation
to 560 passed / 85.68% coverage. Re-run that game's audit and fresh verification
before declaring all fields verified; no live run was performed for this change.

The player-metadata follow-up adds 20 integration cases for skaters and goalies:
580 offline tests pass at 86.07% combined coverage. Real command saves preserve
identity, slugs, saved memberships, gamelogs, draft history and unreported metadata
while refreshing biography/current-roster fields. Country fallback, birthday
boundaries and unknown-code logging are covered. Real flag lookup uses temporary
media; attachment/replay, nationality changes and missing-file recovery are checked.
No application changes were needed for metadata. The career-response follow-up
adds 24 integration cases, bringing validation to 604 passed / 87.53% combined
coverage. Real HTTP helpers and database saves protect current/full source
precedence, replay, partial/zero values and optional-request failure preservation.
A small shared guard rejects malformed JSON/report shapes with a contextual
CommandError before the current player's statistics are saved. HTTP retry policy
and per-player publication remain unchanged.

The player-page follow-up adds 24 integration cases and passes 628 offline tests
at 87.91% combined coverage. Real rendered HTML protects career totals/averages,
current-season visibility, gamelog ordering/PP/SH values, empty states, links and
pager boundaries. Four initially failing invalid-identity cases exposed missing
lookup guards; player detail and gamelog now return 404 instead of server errors.
The profile's existing season-selection behavior is characterized, not extended.
The game-page follow-up adds 16 cases and passes 644 offline tests at 88.02%
combined coverage. Rendered skater/goalie tables use the game's saved date, preserve
roster identity and favorite privacy, and do not substitute season values for
missing gamelogs. Scoreboard contracts cover navigation windows, links, empty data,
calendar-ordered fallback and a fresh Pacific default date on every request.
Six initially failing cases led to narrow view fixes for missing-game/malformed-date
404s, import-time date evaluation and insertion-order fallback. The search follow-up adds 22 integration cases and passes 666 offline tests at
89.11% combined coverage. Existing Players filtering contracts already cover
selected-season projection, sorting, pagination and invalid table requests.
New search/autocomplete checks cover matching/grouping, literal special characters,
empty inputs/results, links and private saved controls. Eleven initially failing
cases led to narrow fixes for blank-term matching, canonical routes, escaped HTML
labels and encoded queries. The private-data follow-up adds 20 cases and passes 686 offline tests at 90.00%
combined coverage. Colliding skater/goalie IDs exposed missing content-type identity;
new notes/positions and profile lookups now use typed ownership. Form errors return
400 without overwriting data, submitted checkbox values are validated, and missing
players return 404. Existing CSRF and anonymous/GET contracts remain checked.
Single unambiguous legacy rows upgrade on edit; ambiguous untyped rows are preserved
but hidden pending explicit review. See [private player data](private-player-data.md).
The measurement-preference follow-up adds 22 cases and passes 708 offline tests
at 90.05% combined coverage. Real profile posts protect USA/Europe persistence,
repeat updates, other-account isolation, invalid choices, login and CSRF. Rendered
skater/goalie profiles and all Players table modes follow saved units, with no
changes to stored player columns or conversion drift when switching viewers.
Existing measurement behavior passed without application changes.

The saved-action follow-up adds 16 integration cases and passes 724 offline tests
at 90.13% combined coverage. Actual quota boundaries, independent comparison groups,
removal/re-addition at capacity, repeated toggles/resets and user isolation now have
real M2M contracts. Four initially failing identity cases led to 404 guards for
favorite/comparison endpoints; the legacy toggle API and quota policy are unchanged.
These tests do not establish concurrent quota enforcement or CSRF protection for
GET-based mutations. The browser foundation now passes three real Chromium cases for Players season
selection, statistics modes and empty seasons. A separate Node lockfile, cached
checksum-verified frontend assets, isolated live server, local browser target and
CI step are implemented. The offline gate passes 725 tests at 90.13%; browser
checks run separately. They exposed and fixed empty metadata checkbox options
that caused jQuery UI errors. See [browser setup](browser-smoke-tests.md).
The saved-list browser follow-up now passes all seven cases, adding real
session-authenticated favorites and comparison interactions with database checks.
It fixes an unavailable-season status label lost outside legacy table-cell markup.
The offline gate remains 725 passed / 90.13% coverage, with browser tests separate.
The team browser follow-up now passes all ten cases. Three new scenarios reuse
traded-player fixtures to protect team-specific values, mode/layout switches,
historical selection and unloaded seasons. Full saved team/player snapshots remain
unchanged, and every team AJAX request retains the selected season. No application
changes were needed. The offline gate remains 725 passed / 90.13% coverage.
The favorites-removal follow-up now passes all fourteen Chromium cases. Four new
scenarios verify last-skater/goalie and final-favorite transitions, counts, selected
season and persistence after reload, without changing other saved lists or player
columns. They exposed unclosed section wrappers and missing empty-group transitions;
the template/controller now handle both. The offline gate remains 725 passed /
90.13% coverage. The AJAX recovery follow-up passes all seventeen Chromium cases:
six injected failures preserve visible data and modes before explicit retries,
including partial failure of a two-request team split. Other memberships and
stored player columns remain intact; no application changes were needed.
The filtered/paginated removal follow-up adds four Chromium cases for skaters and
goalies, protecting global counts, filter/sort/season retention, return to a valid
page and deletion after reload. All twenty-one browser cases pass; application
behavior is unchanged. Hosted CI verification and deployment rehearsal
remain operational priorities; GET-to-POST migration, concurrency policy and
ambiguous legacy-data review stay separate focused work.
The table-rendering follow-up adds nineteen offline cases and fixes escaped
name/tooltip output, balanced player links and missing goalie save-percentage
display. The offline gate now passes 744 tests at 90.24% combined coverage; all
twenty-one Chromium cases still pass. Stored statistics remain unchanged.
The checkbox-rendering follow-up adds twenty-three offline cases, escapes
labels/tooltips/attributes, handles empty selections and protects literal filter
values through real AJAX selection/reset. The gate now passes 767 tests at 90.26%
combined coverage; no stored statistics or dependencies changed.
The malformed-roster batch adds forty-four database cases and validates supplied
rosters before reports or writes. Day rollback, repaired two-game replay and legacy/
unavailable roster compatibility pass. The offline gate now passes 811 tests at
90.46%; changed-participant cleanup is the one remaining planned testing commit
before hosted CI verification and deployment rehearsal.
The changed-participant batch completes that final step with thirty-eight database
cases, verified game-scoped cleanup and conservative legacy guards. The offline
gate now passes 849 tests at 90.55% combined coverage. Further test expansion is
deferred; proceed to hosted CI verification and deployment rehearsal.

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

Implemented: `make update-daily` runs players, current totals and games;
`make update-all` prepends team metadata. Each target uses sequential recipe lines,
so `make -j` retains stage order and a failure prevents subsequent stages from
running. Earlier successful loaders are not rolled back across command boundaries.
`PYTHON=venv/bin/python` can override the interpreter without activating the venv.
Full historical refresh remains explicit. Scheduling remains deferred until manual
runs are reliable.
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

The separate Dependabot dependency-graph run rejected Python 3.7.17
(`tool_version_not_supported`). The validated Python 3.12.16 bridge now updates
the runtime and CI honestly; verify the hosted graph again after pushing.

## 5. Upgrade Django and Python in controlled stages

Retain the agreed checkpoints **2.2 → 3.2 → 4.2 → 5.2**. Read release notes and
resolve deprecations across intervening feature releases; use smaller steps if
needed. The older releases are temporary upgrade checkpoints, not deployment
targets. Django 4.2 support ended in April 2026; Django 5.2 is the intended LTS
endpoint. See the [5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/).

| Checkpoint | Proposed interpreter strategy | Main work |
| --- | --- | --- |
| Django 2.2.28 — complete locally | Python 3.7.17 | Patch baseline, 408 passing tests, unchanged migration state and working-venv dependency update; see upgrade checkpoints. |
| Django 3.2.25 — complete locally | Python 3.10.22 bridge validated | Compatible extensions, core JSONField migration, then Python/Celery/test-tool transition: 414 passing tests and synthetic data-preservation rehearsals. |
| Django 4.2.30 — complete locally | Python 3.12.16 bridge validated | Framework step, then interpreter/dependency transition: 425 passing tests, unchanged migration state, preserved data and profile-upload regressions. |
| Django 5.2.18 — complete locally | Python 3.12.16 | 436 passing tests, preserved synthetic data, compatible forms/storage/toolbar and rehearsed dependency migrations. Hosted/deployment verification remains. |

The bridge choices follow the official compatibility ranges in the
[3.2](https://docs.djangoproject.com/en/3.2/releases/3.2/),
[4.2](https://docs.djangoproject.com/en/4.2/releases/4.2/) and
[5.2](https://docs.djangoproject.com/en/5.2/releases/5.2/) notes. Both interpreter
bridges and the Django 5.2 configuration are now validated locally. Keep future
interpreter changes separate from Django changes wherever possible.

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
4. Completed locally; hosted startup fix awaiting validation: record coverage and add CI. Local commit/
   push test hooks are implemented; follow the per-clone setup in the test guide.
5. Completed: harden game JSON fetching and verify failed-day rollback/replay.
6. Completed locally for this phase: high-value loader/user-flow regression batches
   and the staged Python/Django upgrade.

Use small focused commits with messages explaining both what changed and why.
Item 6 has reached its agreed stopping point: loader persistence/identity/roster
corrections, metadata/career enrichment, user-owned actions, browser workflows and
shared rendering have regression protection. The staged upgrade reached Python
3.12.16 / Django 5.2.18 locally. Next verify hosted CI/dependency-graph results and
rehearse deployment on a disposable representative data copy. Review the next
available 5.2 security patch, then schedule dependency/uv maintenance and optional
edge-case work separately. Keep each change reviewable.
