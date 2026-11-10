# Regression testing and modernization roadmap

Reviewed: 2026-11-10. This records the work agreed in this chat and the remaining
sequence. Update the status and evidence as each small commit lands.

## Goal and recommendation

Upgrade the app from Python 3.7 / Django 2.2 to a supported stack while preserving
loader correctness, historical data and user-facing behavior. Make one focused
change at a time and validate before moving to the next stage.

**Active development: migrate the frontend and JSON API incrementally.** The
[API foundation](api-conventions.md#implemented-api-foundation) and
[saved scoreboard](scoreboard-api.md) and [game-detail JSON](game-detail-api.md)
resources are implemented; the remaining statistics, authentication, account and
saved-list APIs are still pending. Vue 3/Vite/TypeScript is now selected. Complete
the JSON API first, then scaffold frontend/client tooling and migrate the UI.
Loaded-season discovery, the Players catalogue and team metadata/contributions are
implemented, along with public profiles, season histories and gamelogs. Next add
session/CSRF authentication endpoints. Legacy projections need a separate provenance
contract; private notes/position overrides follow in their owned-resource phase. Functionality takes priority
over visual polish;
mobile usability and viewport checks belong in each slice. The
[frontend plan](frontend-architecture.md) estimates 25–30 focused commits for the
whole migration.
Server activation/rehearsal and ambiguous legacy-data review remain deferred. The
[scheduling policy](loader-scheduling.md) records the proposed live/daily/weekly
cadences, current loader limitations and always-on server requirements. The
[legacy inventory](legacy-audit.md) retains deployment/worker usage questions.
Hosted uv CI and dependency-graph
runs have succeeded; deployment backup/restore rehearsal remains deferred.
Django 5.2.18 reached the planned LTS endpoint on Python 3.12.16; the current
offline suite passes 1449 tests at 93.42% combined coverage. The final framework step includes compatible Bootstrap 4 forms, task-result
migrations, removal of broken debug middleware and timezone/storage/auth regressions.
CI reads the same interpreter pin as local uv. The hosted uv dependency graph
completed successfully after the Python transition.
Team persistence and paginated player publication now have database regressions. Totals ordering, history preservation and per-player failure contracts are also covered.
Player biography and flag persistence now have regression coverage as well.
Career-enrichment responses now have HTTP-backed persistence contracts.
The agreed regression-testing phase is complete locally. Keep it as the baseline
and add targeted API/frontend regressions with each migrated workflow rather than
extending the old phase toward 100% coverage. Hosted verification, server activation
and deployment rehearsal remain follow-ups while frontend development proceeds.

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
| Core private-data/preferences and saved-action contracts covered | Auth and user-owned actions | Typed notes/positions, validated profile preferences, ownership and CSRF contracts are covered. Favorites/comparison toggles and resets require POST with CSRF protection and serialize per account using a database row lock. Sequential/concurrent quotas, missing-target 404s, anonymous no-writes, rollback and reset isolation have persistence tests. |
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
These initial tests did not establish concurrent quota enforcement or CSRF protection
for GET-based mutations; the POST/CSRF follow-up below closes the latter gap.
The browser foundation now passes three real Chromium cases for Players season
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
remain operational priorities; the later POST/CSRF follow-up completes GET-to-POST
migration. Concurrency policy and ambiguous legacy-data review remain focused work.
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
Full historical refresh remains explicit. The later
[server scheduling policy](loader-scheduling.md) separates live refreshes from
heavy batch work; automation remains disabled pending targeted-loader and
coordination implementation.
The reported current-totals HTTP 429 now has a shared bounded retry policy across
supported loaders: seconds/date `Retry-After`, exponential backoff, finite timeouts,
fail-fast permanent HTTP errors and explicit failure on persistent rate limits.
Optional career data and season detection cannot swallow an exhausted 429.
Image/report downloads share the same policy; the audit retains its existing pacing
and checkpoint behavior. See [HTTP policy and reruns](loader-http.md).
After a successful refresh verify the new season on Players, teams and saved
lists; absence of a season row must not display an older snapshot as current.

## 4. Reproduce dependencies and choose the uv transition

The HTTP/TLS security batch updates certifi to 2026.10.18, Requests to 2.33.0,
urllib3 to 2.8.0 and idna to 3.15. These published, non-yanked releases support
Python 3.12 and put the pins outside the affected ranges of nine open alerts,
including the [critical emSign CA-bundle alert](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2). A clean environment passes
`pip check`, 893 offline tests (90.86% combined coverage) and all 21 Chromium cases.
The loaded trust store excludes emSign roots; real local HTTPS validation still
rejects untrusted certificates. Hosted alert closure awaits push and rescanning.
The Pillow security batch updates 10.4.0 to 13.0.0, a published, non-yanked release
supporting Python 3.11+ and the project's Python 3.12.16 runtime. Its pin is outside
the affected ranges of all 52 current Pillow alerts, including the
[critical FPX/JPEG decoding alert](https://github.com/python-pillow/Pillow/security/advisories/GHSA-5x8w-8jj5-q52h).
A clean environment passes `pip check`, 902 offline tests at 90.86% combined
coverage and all 21 Chromium cases. Profile-upload regressions now protect PNG,
JPEG and WebP decoding/storage, invalid/truncated/disguised SVG rejection,
decompression-bomb limits and existing avatar/account preservation. No application
image policy or decoder-limit settings change. Alert closure requires push/rescan;
running environments must install requirements and restart.
The legacy MySQL shim is now removed: repository search found no MySQL callers
beyond package startup, and all configured database backends use PostgreSQL.
`PyMySQL==0.9.3` is removed from requirements instead of upgrading an unused driver.
Django/WSGI/PostgreSQL initialization and the Celery app export are checked with
MySQL imports forbidden; a clean environment without either MySQL driver passes
dependency, system/migration, offline and Chromium checks. This addresses
[PyMySQL alert #15](https://github.com/edvard-munch/nhl-statso-maniacs/security/dependabot/15)
once the changed requirements reach the default branch and GitHub rescans.
The SQL/progress security batch updates sqlparse 0.5.3 to 0.6.1 and tqdm 4.36.1
to 4.70.1. These published, non-yanked releases support Python 3.12, cover the
affected ranges of seven current alerts and pass clean-install, PostgreSQL
system/migration, 902 offline and 21 Chromium checks. sqlparse 0.6.1 includes
additional security fixes beyond 0.6.0. Its maintainer also announced
[end of maintenance](https://sqlparse.readthedocs.io/en/latest/changes.html#release-0-6-1-nov-01-2026);
track Django's dependency guidance and future security implications separately.
Django still requires sqlparse, so removing its explicit pin would not remove the
dependency.
The packaging security batch updates pip 24.0 to 26.3, setuptools 75.8.0 to
84.2.1 and wheel 0.42.0 to 0.48.0. These published, non-yanked Python 3.12-compatible
pins cover all ten current packaging-tool alerts. Wheel's new runtime dependency
requires raising packaging 23.2 to 26.3 in both bootstrap and project requirements.
A fresh bootstrap/project/hook install passes dependency, PostgreSQL system/
migration, 902 offline and 21 Chromium checks, retaining 90.86% combined coverage.
Local wheel build/unpack/install and uncached legacy source builds also pass.
No CI command changes are needed: it already installs bootstrap requirements first.
See [environment update commands](testing.md#python-environment). Alert closure
still requires a default-branch push and rescan.
The legacy documentation chain is now retired: the app uses Django templates,
and maintained documentation is Markdown linked from the README. The old Sphinx
index referenced a missing `modules` document and its config hardcoded another
machine's Python 3.6 paths. That unused scaffold and its 19 dependency pins are removed,
including redundant Napoleon/pockets and Python metadata backports that no active
dependency needs on Python 3.12. The removed Jinja2/Babel/Pygments/zipp pins account
for eleven current alerts; closure requires pushing and rescanning. See
[existing venv cleanup](testing.md#python-environment).
The pytest security follow-up updates pytest 7.4.4 to 9.2.0, above alert #54's
fixed version 9.0.3, and Pluggy 1.3.0 to 1.7.0 to meet its dependency requirements.
Pygments returns as a patched 2.21.0 pin because current pytest requires it for
terminal highlighting; the obsolete Sphinx chain remains retired. Existing Django
and coverage plugin pins, test selection and hook commands remain unchanged.
Fresh-install dependency and Django checks pass, as do both 902-test hook modes
and all 21 Chromium cases, retaining 90.86% combined coverage. Three existing
requests-mock deprecation warnings were visible at plugin startup. The follow-up
updates requests-mock 1.8.0 to 1.12.1, replacing the plugin's deprecated distutils
version comparison with numeric tuple comparison; no warnings are suppressed.
Both suites pass without warnings: 902 offline tests at 90.86% combined coverage
and 21 Chromium cases; dependency and Django checks also pass.
Alert closure still requires a default-branch push/rescan.

The first [uv checkpoint](uv-migration.md) adds project metadata alongside Ruff
configuration and commits `uv.lock`. All 64 existing unique requirement pins are
preserved across runtime, test, hook and development groups. The app is a virtual
checkout project, with Python restricted to the validated 3.12 minor and isolated
build constraints matching the bootstrap tools. A clean uv 0.10.10 default sync
has the same 74 installed versions as the validated pip environment. Runtime-only
sync, dependency checks, Django/migration/WSGI/Celery checks, 902 offline tests at
90.86% combined coverage and 21 Chromium cases pass using disposable environments
and PostgreSQL. Existing venv, requirements, Make commands, hooks and CI are
unchanged in that first checkpoint.
The workflow follow-up now runs Make, hooks and CI through `uv run --locked`.
Hooks invoke uv directly instead of searching legacy/active venvs; missing uv,
lock/sync failures and invalid test configuration block execution without fallback.
CI pins uv 0.10.10 and caches by the lockfile. `requirements.txt` is generated from
that graph with artifact hashes and a CI drift check; redundant bootstrap/hook
requirements files are retired. All package versions and the lockfile are unchanged.
Clean sync, stale-lock/export guards, loader sequencing, both real test hooks in a
temporary Git checkout, 902 offline tests at 90.86% coverage, 21 Chromium cases and
XML export pass locally. Reinstall hooks in each clone with `make hooks`; uv must
be on terminal/GUI PATH. Hosted Actions still needs verification after push.

Correction to the earlier chat advice: current uv documentation lists Python
3.7 as Tier 2, rather than universally excluding it. That does **not** prove this
project's dependency resolution, `uv sync`, or interpreter provisioning will work.
Validate the exact uv version and workflow in a fresh environment before changing
the standard setup. See [uv Python support](https://docs.astral.sh/uv/reference/policies/python/).

The baseline, Python/Django bridge and metadata/lockfile validation are complete
locally, including the Make/hook/CI workflow switch. Next verify hosted CI and
Dependabot's uv/dependency graph after push, then return to the separately queued
optional live checks, legacy audit and behavior changes. Deployment backup/restore
rehearsal remains deferred. Keep dependency/framework upgrades in separate commits.

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

The [optional live API contracts](live-api-checks.md) are repaired and pass all
22 cases against current sources. They use production readers/parsers, a completed
reference season/game and a paced read-only session, without key-order or mutable
count assumptions. `make test-external` runs them explicitly and stops on the first
failure; normal tests, hooks and CI remain offline. The default suite still passes
902 tests at 90.86% coverage, now deselecting 22 external and 21 browser cases.
The [legacy inventory](legacy-audit.md) now classifies the nine tracked discoverable
commands and six `_new` experiments, their data/UI consumers and dependency chains.
It records no repository scheduler for the Celery updater, whose sequence omits
current totals, and the Procfile's undeclared Gunicorn dependency. No scripts,
dependencies or data are removed. Confirm machine/host usage before selecting a
cleanup batch. The legacy projection and video fields still have UI consumers;
removing obsolete live assertions does not repair their writer commands.
The first cleanup follow-up removes only `mccabe`, `pycodestyle` and `pyflakes`
from the development group, lockfile and generated requirements. Ruff stays the
configured linter/formatter, and every retained dependency version is unchanged.
The separate test compatibility cleanup removes only `attrs`, `more-itertools`,
`py` and `pyparsing`, retaining all other versions. `django-shortcuts` is explicitly
kept for the confirmed `django r` / `m` / `mm` developer workflow.
The six confirmed unused `_new` experiments are now removed. They had no tracked
callers and were excluded from normal Django command discovery; several contained
legacy data writes and unusable sampled endpoints. The inventory retains their
purpose and findings as history. No top-level commands, stored fields/data,
fixtures, OAuth files or dependencies are removed in this retirement batch.
The following batch retires `upd_pls_proj`, `upd_vids`, `upd_pls_sbs-n` and
`json_fixtures_creator`, plus the projection-only mocked transport case. Stored
fields/UI, fixture exports, OAuth files, task/Make orchestration and all dependency
pins remain. The audit records separate review decisions for furl/orderedmultidict,
six legacy exports and 22 OAuth-related JSON files; no authenticated request or
credential validation is part of command retirement.
A separate dependency follow-up removes furl and orderedmultidict, whose only
code consumer was the retired video command. No remaining package versions,
fixture exports, OAuth files or app behavior change; django-shortcuts stays.
The next artifact cleanup removes six unused `players/fixtures/*_objects.json`
exports and the disabled historical `loaddata` block/import. Supported tests use
their own synthetic fixtures; no application data, models, migrations, active
test fixtures, OAuth files or dependency settings change. OAuth retention is a
separate review rather than an implied part of retiring old data exports.
The [OAuth artifact review](oauth-file-review.md) is now documented without secret
values. The public repository contains eleven web-client configurations with
secrets, ten access/refresh-token stores and one empty file. Access-token expiry
dates alone do not establish that refresh grants are revoked. Next the owner
must verify project/account usage and revoke/rotate the retired credentials;
file deletion/ignore rules and any coordinated history cleanup remain separate.
After the user confirmed the OAuth artifacts are unused, all 22 JSON files are
deleted and the retired directory is ignored. No credential is used or revoked,
and Git history is unchanged. Revocation/rotation by the owner and any coordinated
history cleanup remain outstanding; repository deletion alone does not resolve
the prior exposure. App data/UI and dependencies are unchanged.
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
7. Completed: uv metadata, lockfile and local/hook/CI workflow migration; hosted
   uv CI and dependency-graph success confirmed.
8. Completed: repaired opt-in live API contracts; 22 live checks pass separately.
9. Inventory complete: [legacy command/dependency audit](legacy-audit.md). Next
   confirm external usage, then select focused cleanup/repair commits without
   removing stored fields or changing task behavior implicitly.

Use small focused commits with messages explaining both what changed and why.
Item 6 has reached its agreed stopping point: loader persistence/identity/roster
corrections, metadata/career enrichment, user-owned actions, browser workflows and
shared rendering have regression protection. The staged upgrade reached Python
3.12.16 / Django 5.2.18 locally, followed by the verified hosted uv workflow and
repaired live contracts. Use the legacy inventory to choose the next cleanup batch.
Deployment rehearsal on a disposable representative data copy remains deferred;
framework patches and behavior changes remain separate focused work.

## Saved-player POST/CSRF follow-up

Favorites/comparison toggles and comparison resets now require POST and CSRF
validation. Shared AJAX setup sends the masked token only to the same origin;
table reads and mode switches remain GET. Canonical favorite URLs avoid POST
redirects. Eighteen new offline cases and one new Chromium case verify rejection,
persistence and actual request headers. Disposable PostgreSQL checks pass:
919 offline tests at 91.28% coverage and all 22 Chromium cases. See
[saved-list request contracts](saved-player-season-tables.md#saved-list-requests).
The concurrency follow-up below completes quota enforcement. Ambiguous legacy-data
decisions remain separate behavior changes; deployment rehearsal remains deferred.

## Concurrent saved-list quotas

Favorites/comparison toggles and comparison resets now share an atomic user-row
lock before reading membership or quota usage. It covers empty lists and mixed
skater/goalie favorites across requests and workers, without serializing unrelated
accounts. Quotas remain 100 favorites combined and five comparisons per player
type; no schema migration or automatic trimming of existing data is introduced.
Comparison payload failures roll back membership changes.

Twenty-three PostgreSQL transaction cases verify actual lock waits on independent
connections, final-slot contention, same-player toggles, removal/addition, both
reset/toggle orders, independent accounts and rollback. The full offline suite
passes 942 tests at 91.30% coverage, with all 22 Chromium cases passing. See
[concurrency behavior and writer requirements](saved-player-season-tables.md#concurrent-changes).
Ambiguous legacy-data review and deployment rehearsal remain separate work.

## Server scheduling plan

The owner confirmed Celery is not running and should be set up on an always-on
server. The [scheduling policy and server requirements](loader-scheduling.md)
document proposed live-game polling every 2–5 minutes, bounded final-game retries,
daily player/current-totals/recent-game reconciliation and weekly teams. Cadences
remain provisional; full historical refresh stays manual. No jobs or services are
enabled by the policy commit.

Targeted game/date refreshes are now implemented as recorded below.
Shared overlap protection and run history are implemented below. Cross-run
cooldown and scheduler policies are completed by the task-split follow-up below.
Browser freshness is implemented below; next validate the host's broker/Beat/services.
Host/broker choice, exact live freshness, intra-game season-table needs and quiet
windows must be confirmed before activation. Existing manual Make targets and
the legacy Celery task retain their current behavior until those focused commits.

## Targeted game refreshes

`upd_gms --date ...` and `--game-id ...` accept repeated explicit selectors and
started/active/final filters. They avoid broad scanning, defer known pregame games,
replay finished games and publish per game after fetching required data. Missing
report fields retain valid same-game values; otherwise they remain unknown and
render as dashes. Targeted subsets cannot promote whole-day completion. Saved
date/identity conflicts require explicit reconciliation. No-argument broad
refresh and Make/Celery sequences retain their existing behavior.

Forty-six new mocked-HTTP/PostgreSQL cases reuse the roster/report fixtures.
System/migration checks, 988 offline tests at 91.44% coverage and all 22 Chromium
cases pass against disposable PostgreSQL. See [targeted contracts and commands](game-loading.md#targeted-game-and-date-refreshes).
The overlap/run-status follow-up below adds coordination and progress. Cross-run
cooldowns remain before task splitting and enabling Beat. No periodic jobs or
server services are enabled yet.

## Loader overlap protection and run history

Supported writer command entry points share a non-waiting PostgreSQL session
advisory lock across manual/Make/Celery execution, including TOI repair. Busy
invocations record skipped and fail before requests/publication. Migration 0048
adds durable scope/status/timing/progress history; stderr JSON events, application
logging and `loader_status` expose runs without changing existing stdout payloads.
Session changes fail closed, and the next lock owner marks abandoned runs
interrupted after a hard exit. Existing publication transaction boundaries remain.

Twenty-one new isolated PostgreSQL tests cover cross-command contention, failure,
interruption, session loss, actual process termination, progress/status reads and
eager Celery integration. Writer-command regression tests now use committed
transactions rather than a wrapping test transaction. System/migration checks,
1009 offline tests at 91.64% coverage and all 22 Chromium cases pass. See
[rollout, limitations and status commands](loader-runs.md).
The task-split follow-up below adds shared cross-run cooldowns, retry/expiry
handling and broker/Beat configuration. Scheduling stays opt-in.

## Celery task split and opt-in scheduling

Separate discovery/live/final/daily/weekly/cleanup tasks now use persisted schedule
state, finite final-retry windows and job locks. Daily work enforces weekly or
bootstrap teams before players, current totals and three recent final schedule
dates. Quiet-window checks, expiring publications and completion/attempt markers
limit duplicate or stale work. Exhausted 429s establish a shared persisted cooldown
for manual and scheduled writers; scheduled busy/cooldown results are deferred,
with no immediate whole-task retries. The legacy task name/body is retained and
is not scheduled.

Migration 0049 adds schedule/control tables. RabbitMQ configuration uses existing
dependencies; Beat is explicitly UTC and disabled by default. Service examples,
environment options and retention/startup instructions are in
[Celery operation](celery-operations.md). Actual broker provisioning, activation,
host service health and backup/restore rehearsal remain unverified host work.
Thirty-three new isolated cases protect configuration, persistent selection,
quiet/order/failure rules, DST dates, cooldowns, retention and job coalescing.
System/migration checks, 1042 offline tests at 91.68% coverage and all 22 Chromium
cases pass. Browser refresh/freshness is implemented in the follow-up below.
Next validate controlled server activation. Ambiguous legacy-data review remains separate.


## Browser auto-refresh and saved-data freshness

Game detail and scoreboard views now poll read-only, private/no-store endpoints
once a minute while visible. Saved timestamps are distinct from browser checks;
unfinished data older than 15 minutes and missing saved supplementary/player fields
are labelled. Final historical data is not stale merely due to age. Manual retry,
pause, hidden-tab suspension and bounded failure backoff keep the current data
visible through failures. Table sorting/focus, the selected scoreboard day and
favorite mutations are preserved, including an overlapping POST/refresh response.
Browser polling never starts loaders or fetches NHL data.

Eight new isolated database cases and four new Chromium scenarios cover these
contracts. The offline gate passes 1050 tests at 91.80% combined coverage, with
the existing 35% gate unchanged. All 26 Chromium cases and system/migration checks
also pass. See
[browser freshness operation](celery-operations.md#browser-refresh-and-freshness).
Server broker/worker/Beat activation, a controlled live refresh, service health and
backup/restore rehearsal remain host validation work; no services are enabled by
this change. Ambiguous legacy-data review remains separate.


## Unattended-operation logging

Shared UTC JSON handlers now collect loader, HTTP, scheduler and Celery/pool
messages with task/job/run correlation, lifecycle duration/outcomes and failure
tracebacks. Error/interruption severity and scoped context cleanup are covered;
command stdout, transaction behavior and scheduling decisions are unchanged.
Service examples select journald; optional namespace retention and file-logrotate
examples require host installation/review. The offline gate passes 1064 tests at
91.82% coverage, including 14 added cases/variants; 72 focused cases pass. See
[logging operation](celery-operations.md#logging-and-retention). Host activation,
retention verification and overdue/failure monitoring remain deployment work.


## Read-only scheduler health

`scheduler_health` now exposes saved configuration, success markers, due/overdue
work, cooldowns, recent unresolved failures and long-running loaders in terminal
or versioned JSON form. Exit codes distinguish healthy/unhealthy/disabled/unknown.
Health and execution share game selection; checks neither initialize state nor
probe services or acquire writer locks. Twenty-five new cases and the full offline
gate pass: 1089 tests at 92.04% coverage; 79 focused cases pass. See
[health semantics and monitoring](scheduler-health.md). Alert delivery and live
broker/worker/Beat/service validation remain deployment work.


## Frontend architecture and API planning

The separate-frontend phase has a documented Nuxt/Vue working proposal, API-only
Django boundaries, same-origin session/CSRF design, typed OpenAPI/client strategy,
season/statistics/null/unit conventions and a staged 25–30-commit migration budget.
Rendering selection and the Django-admin HTML exception remain explicit decisions;
no new dependencies, routes, database changes or frontend implementation are
introduced by these documents. Existing regression results remain unchanged.


## JSON API foundation and schema

DRF 3.18.3 and drf-spectacular 0.30.0 now provide `/api/v1/` private version
metadata and a public JSON OpenAPI schema. Shared session/CSRF policy, typed
error envelopes, API-scoped Django/middleware normalization and request-ID
correlation leave legacy HTML/AJAX contracts intact. Schema export validates
without database queries or live HTTP; no resource/auth lifecycle migration is
claimed yet. The typing-extensions pin moves from 4.5.0 to 4.16.0 to fix the
schema validator's Python 3.12 import failure; Django/Python pins are unchanged.

Thirty-nine new contract cases pass, along with 1128 offline tests and all 26
Chromium cases on rerun. System/schema, lint/export and dependency checks pass.
The 92.04%/35% coverage result retains the existing `players` scope; project API
helpers are tested but outside that percentage. The initial concurrent browser
run had one initial-table timeout with unfinished local script loads; no frontend
change was made and the standalone repeat passed. Next add the saved scoreboard
JSON resource, preserving the existing loader/freshness contracts.


## Saved scoreboard JSON resource

`GET /api/v1/games/?date=YYYY-MM-DD` now reads exact-date saved games with explicit
team/score serializers, bounded page-number pagination and per-game/whole-date
freshness. Invalid/duplicate/unsupported query parameters fail before queries;
empty dates never fall back to another day. Public responses have no personal
fields, template rendering, upstream calls or application writes. Nonempty reads
use two SELECTs with prefetched historical side associations.

The current model stores scores only in `Game.result`. A conservative adapter
accepts the exact known loader label with unambiguous away/home sides and exposes
`score_source=legacy_result`; unverifiable scores remain null/partial. This is
not a structured-score persistence migration. See [contract and limitations](scoreboard-api.md).
Forty new cases pass with the full offline gate: 1168 tests, 48 deselected,
92.20% combined players coverage; the 35% gate/scope are unchanged. System/schema,
lint and dependency-export checks pass. All 26 Chromium cases pass on repeat
after an initial local-script `net::ERR_NETWORK_CHANGED` failure, with no test or
application change for the repeat. The next API slice is saved game detail;
frontend rendering selection and actual service rollout remain separate decisions.


## Saved game-detail JSON resource

`GET /api/v1/games/{nhl_id}/` now shares the scoreboard's saved summary adapter
and adds explicit typed away/home rosters and date-scoped statistics. It validates
nested player identity and game markers, checks unstamped legacy team/appearance
evidence in batches, and retains roster identities with null statistics when rows
are missing or unverified. Counts/TOI/fractions have documented units and nullable
validation; profile snapshots, other dates and private state are not fallbacks.

PostgreSQL extracts only the requested gamelog date; prefetched roster groups use
eight SELECTs, or at most ten with legacy collision checks. No loader, HTTP call,
HTML rendering, application write or writer lock is introduced. Existing HTML
pages, scoreboard JSON and authentication boundaries remain covered. See
[game-detail contracts](game-detail-api.md). Fifty-one new cases and the full
offline gate pass: 1219 tests, 48 deselected, 92.44% combined players coverage;
35%/scope are unchanged. All 26 Chromium cases and schema/system/migration,
lint and export checks pass. Frontend rendering/scaffolding and actual service
activation remain separate work.


## Frontend choice confirmed — 2026-11-10

Use Vue 3/Vite/TypeScript with browser rendering. Prioritize functional parity and
mobile usability before visual polish. The game APIs support the first frontend
pilot; they do not complete the API migration. Subsequent workflows still need
their JSON endpoints and frontend replacements. See the current scope and mobile
acceptance requirements in the [frontend plan](frontend-architecture.md).


## Loaded seasons API — 2026-11-10

`GET /api/v1/seasons/` exposes normalized, deduplicated loaded NHL regular-season
SBS seasons with pagination and a global nullable default. Discovery and labels
are extracted into `players.seasons`, shared with legacy pages; snapshot fields,
averages and calendar dates do not establish availability. Strict pagination now
rejects explicit blanks instead of silently substituting defaults. The contract
and limitations are documented in [loaded seasons API](seasons-api.md).

Sixteen new integration cases and the full offline gate pass: 1235 tests,
48 deselected, 92.24% combined players coverage against the unchanged 35% gate.
Schema validation, Django system/migration checks, lint/formatting and dependency
export checks pass. API-first development is recorded; next implement the Players
catalogue before starting Vue/Vite.


## Selected-season Players catalogue API — 2026-11-10

`GET /api/v1/players/` now exposes a public typed skater/goalie catalogue using the
shared SBS reader. Positive known games establish membership; snapshots, stored
averages and another season never supply missing values. Named filters and
allowlisted sorting run before pagination, season participation drives team
filters, and deterministic NHL identity ties replace database insertion order.
Skater totals/averages and goalie counts/rates have explicit discriminated OpenAPI
shapes, documented units, nullable invalid values and current biography/media URLs.
Private state and raw histories are excluded. No writes, upstream requests,
dependencies or migrations are introduced; legacy tables remain unchanged.

Seventy-four new cases extend the season fixtures. The focused run passes 201
tests. The full repeat passes 1309 tests, 48 deselected, at 92.94% combined players
coverage against the unchanged 35% gate/scope. The initial full run hit the existing
loader child-process 10-second startup timeout; its 21-test file and the full
repeat pass without changing that test or loader behavior. Schema/system/migration,
formatting/lint and dependency-export checks pass. No frontend/browser change is
introduced. See [Players API contract](players-api.md). Next add teams and
selected-season team contributions, continuing API-first development.


## Team metadata and season-contributions APIs — 2026-11-10

`GET /api/v1/teams/`, `/api/v1/teams/{nhl_id}/` and the paginated
`/api/v1/teams/{nhl_id}/players/` now expose saved metadata and exact team-season
contributions. Team detail links preserve the resolved global season. The shared
catalogue accepts a scoped team, narrowing candidates with JSON containment and
reading the exact SBS split; current roster links, combined-only rows and other
seasons do not supply missing contributions. Statistics, filters, ordering,
pagination and public identity reuse the Players API contract, with a current
profile jersey number on team entries. Legacy tables remain unchanged.

Sixty new cases extend the team/trade fixtures. The focused API/legacy run passes
284 tests; the full offline gate passes 1369 tests, 48 deselected, at 93.13%
combined players coverage against the unchanged 35% gate/scope. Schema, system,
migration-drift, lint/formatting and dependency-export checks pass. Reads have
bounded query counts and no writes or NHL calls. No dependencies, migrations or
frontend changes are introduced. See [Teams API contract](teams-api.md). Next add
public player profiles and gamelogs before frontend scaffolding.


## Typed player profiles, season history and gamelogs — 2026-11-10

Public typed profile, `/seasons/` and `/gamelog/` resources now expose biography,
current team, selected SBS season and separate saved career packets. Season history
uses the shared reader for overall statistics and exact contributions; career
aggregates remain independent of SBS completeness and selection. Typed identity
does not infer model type from position. Known profiles remain available with
missing/zero-game seasons. Private state, raw JSON and legacy projections are
excluded; projections need a separate season-provenance/derivation contract.

Gamelogs share the game-detail verification helper, use batched typed roster
membership/collision evidence, and retain orphan, missing and ambiguous rows with
explicit availability and null statistics. Named statistic/date/team filters and
ordering run before pagination. Invalid counts/rates and missing TOI remain null;
actual game durations are seconds. Profile/history/gamelog schemas document typed,
nullable responses. Legacy rendered views and existing APIs remain covered.

Eighty new cases extend the existing season/trade/game fixtures. The focused run
passes 439 tests; the full offline gate passes 1449 tests, 48 deselected, at 93.42%
combined players coverage against the unchanged 35% gate/scope. Schema, system,
migration-drift, formatting/lint and dependency-export checks pass. No dependencies,
migrations, application writes or NHL requests are introduced. See the
[player profile contract](player-profile-api.md). Next add session/CSRF auth APIs;
private owned resources follow. Frontend scaffolding remains deferred.
