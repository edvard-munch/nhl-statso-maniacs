# Offline coverage baseline and CI

Measured on 2026-11-03, after repairing collection, database isolation and request
mocks. The pre-change application baseline is commit `c35260d`; this change adds
CI/configuration/docs without changing application behavior or coverage exclusions.

## Measured results

| Check | Result |
| --- | --- |
| Default suite | 336 passed; 12 external tests deselected |
| Line coverage | 2,197 / 2,855 executable statements: **76.95%** |
| Branch coverage | 753 / 1,097 branches: **68.64%** |
| Combined coverage | (2,197 + 753) / (2,855 + 1,097): **74.65%** |
| Initial gate | **35%, passed**, unchanged |
| `make test-cov` | Passed in the existing environment |
| `make test-ci` | Passed in existing and freshly installed environments |

Coverage.py rounds the terminal summary to 75%; pytest-cov reports the more
precise gate result as 74.65%. With branch coverage enabled, the gate compares
the combined metric, not the line-only figure.

Both local environments used Python 3.7.17, Django 2.2.6, pytest 5.4.2,
pytest-django 3.9.0, pytest-cov 2.12.1 and coverage 7.2.7. Tests ran against
disposable PostgreSQL 16 clusters and used real migrations. The application
database was not accessed. The fresh environment was created without system
site packages and installed all requirements using the pinned bootstrap tools;
`pip check` and Ruff passed. Dependency pins were not upgraded.

The existing `.coveragerc` measures `players` with branch coverage and excludes
tests, migrations and the existing configuration/entry-point patterns. Neither
that scope nor the threshold was narrowed to obtain a passing result. The Make
targets select `players/tests`; this does not measure user-app or JavaScript/browser
coverage. Module imports can contribute coverage without proving every behavior.

## What the results suggest doing next

The season reader and new table/loader modules have strong focused coverage.
The largest remaining loader gap is `upd_gms` (53% combined coverage), particularly
network failures and command/database orchestration. The reported JSON decoding
failure is therefore the next focused fix: test empty/HTML/error responses, add
bounded request handling with game context, and protect replay/persistence behavior.
Totals enrichment, user-owned edits and other user-facing flows still have gaps.
See the [roadmap](modernization-roadmap.md) for the remaining order of work.

Keep 35% as the agreed initial floor for this commit. Raising it can be a separate
reviewed change; a passing aggregate percentage does not replace checking important
failure paths.

## CI and reproduction

Follow [test setup](testing.md) to activate the environment and use dedicated test
credentials, then run:

```bash
make test-cov
make test-ci
```

The GitHub Actions workflow now uses Ubuntu 22.04, Python 3.12.16 and an isolated
PostgreSQL 16 service exposed on localhost:5432. It installs the verified
`requirements-bootstrap.txt` tools, installs `requirements.txt`, runs `pip check`,
Ruff and syntax checks for the four season-table JavaScript controllers, and runs
`make test-ci`. pytest-django creates `test_nhl_ci` with real migrations; no loader
commands run and live API tests remain excluded. The workflow uses read-only
repository permissions, no application secrets and no deployment steps.

After tests, CI exports `coverage.xml` and uploads it as `coverage-python312` for
14 days. Generated XML and coverage data are ignored by Git. Workflow syntax and
expressions passed actionlint 1.7.7 validation; the dependency install, static checks,
coverage command and XML export were validated locally. The first hosted test
run on `b55ab9d` failed during logging setup because `logs/` was missing. The
follow-up below repairs fresh-checkout startup; a hosted run of that fix is still
pending. Local validation does not establish a remote CI run passed.

References: [GitHub's PostgreSQL service guidance](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)
and [setup-python](https://github.com/actions/setup-python/tree/v6).

## Follow-up: game request handling

After adding request-failure and gameday transaction regression tests, the full
push-stage coverage hook passes **379 tests**, with 12 external tests deselected
and **76.88% combined coverage**. `upd_gms` rises to 65% combined coverage. The
original baseline table above is retained as a historical checkpoint. Remaining
game roster/gamelog persistence and command orchestration are still priorities.

## Follow-up: roster/gamelog persistence

The next database-contract batch passes **397 tests**, with 12 external checks
deselected and **82.53% combined coverage**; `upd_gms` reaches 93%. It covers real
roster relations, enrichment precedence, historical gamelogs, saved memberships,
missing/bench/shared goalies, command replay and rollback after player writes.
The tests also exposed and repaired premature live-game completion and stale
finished-day flags. The threshold remains unchanged at 35%.

## Follow-up: report identity

The player-ID/team-scoping fix passes **407 tests**, with 12 external checks
deselected and **82.59% combined coverage**. New regressions prevent shared jersey
numbers from mixing opponents' special-team points or TOI. Ambiguous unscoped HTML
rows are skipped with warnings; missing counting fields keep existing defaults.
The coverage gate remains 35%.

## Hosted startup failure and clean-checkout reproduction

[Hosted run 41619757606](https://github.com/edvard-munch/nhl-statso-maniacs/actions/runs/41619757606)
failed before test collection: the file logging handler could not open
`logs/nhl_web_app.log`. The local workspace already contained `logs/`, which hid
this missing-directory dependency in earlier local validation.

Settings now create the log directory before configuring the handler. A regression
starts Django twice in a fresh temporary project location, with HTTP/database
access blocked, and verifies both startup messages reach the new log file. The
complete suite also passes from a clean temporary checkout containing no runtime
logs, `.env`, or venv: **408 passed, 12 external tests deselected, 82.59% combined
coverage**, using the fresh Python environment and disposable PostgreSQL. XML
export succeeds. Workflow conditions skip export/upload when input files are
absent, and upload-artifact v6 uses Node 24. The repaired hosted workflow must be
validated after the fix is pushed.

A separate [Dependabot graph run](https://github.com/edvard-munch/nhl-statso-maniacs/actions/runs/41619761779)
failed with `tool_version_not_supported`: its service rejects the repository's
Python 3.7.17 pin and lists Python 3.10+ in that run. This is independent of the
test workflow. Keep the honest interpreter pin and resolve that limitation during
the planned Python transition; no repository automation settings were changed.

## Upgrade checkpoint: Django 2.2.28

The first framework patch update keeps Python 3.7.17 and passes **408 tests**,
with 12 external tests deselected and **82.59% combined coverage**. System checks
and model/migration drift checks pass for both Django 2.2.6 and 2.2.28; the isolated
schema migrated under 2.2.6 requires no new migrations after the patch. See
[upgrade checkpoints](django-upgrade-checkpoints.md). The Python 3.7 dependency-
graph blocker remains until the later interpreter step.

## Upgrade checkpoint: Django 3.2.25

The framework compatibility step keeps Python 3.7.17 and passes **409 tests**,
with 12 external checks deselected and **82.58% combined coverage** through the
full push-stage hook. The extra regression exercises the core JSONField migration,
JSON containment queries and saved memberships. The small coverage change reflects
the changed source denominator; the gate and exclusions are unchanged. The isolated
old-to-new migration rehearsal preserves synthetic player and user data; see
[upgrade checkpoints](django-upgrade-checkpoints.md). The working venv is updated,
but the application database still needs `manage.py migrate`. Dependabot's Python
3.7 blocker remains for the separate interpreter transition.

## Upgrade checkpoint: Python 3.10.22

The interpreter bridge retains Django 3.2.25 and passes **414 offline tests**, with
12 external checks deselected and **82.79% combined coverage**. This includes the
full managed push hook and a clean-checkout reproduction with XML export. Five
new Celery regressions cover loader order, stopping on failure and database-result
updates/decoding without a broker. Coverage remains 7.2.7, and the gate/exclusions
are unchanged; source denominators also differ across Python interpreters.

Both CI and local pyenv now use the validated 3.10.22 pin. The synthetic migration
rehearsal preserves supported task-result values and player/user data; upstream
Celery-result migrations remove the old `hidden` flag. See
[upgrade checkpoints](django-upgrade-checkpoints.md). The hosted dependency graph
must be rerun after pushing to confirm the original version error is resolved.

## Upgrade checkpoint: Django 4.2.30

The framework step retains Python 3.10.22 and passes **423 offline tests**, with
12 external checks deselected and **82.79% combined coverage**. Nine new regressions
cover auth-form rendering, user/profile creation, HTTPS login/CSRF, POST logout
with safe redirects and development-toolbar rendering. The measured scope remains
`players`; user-app tests do not expand that coverage denominator. The initial
35% gate and exclusions are unchanged.

The old-to-new synthetic database rehearsal preserves player/user/task-result
values and shows no new migrations. See
[upgrade checkpoints](django-upgrade-checkpoints.md). Hosted CI must still be
checked after pushing.

## Upgrade checkpoint: Python 3.12.16

The interpreter bridge retains Django 4.2.30 and passes **425 offline tests**,
with 12 external checks deselected and **82.51% combined coverage**. This includes
profile upload/invalid-image regressions for the Pillow change. Python-sensitive
dependencies, including coverage 7.6.12, are pinned in `requirements.txt`.

The 35% gate, measured packages and exclusions are unchanged. Python 3.12 and the
new tracer report a different branch denominator (956 instead of 1,131), so the
percentage is not directly comparable with the preceding 82.79% measurement.
The source statement totals and missed-statement counts remain 2,914 and 434.
The clean-checkout CI reproduction exports XML successfully, and the synthetic
database rehearsal shows no new migrations or changed player/user/task data.
See [upgrade checkpoints](django-upgrade-checkpoints.md). Hosted CI and the
dependency graph still require verification after pushing.

## Upgrade checkpoint: Django 5.2.18

The LTS endpoint passes **436 offline tests**, with 12 external checks deselected,
**82.56% combined coverage** and no test warnings on Python 3.12.16. Eleven new
cases cover password reset using in-memory email, Pacific date boundaries and
file overwrite behavior after the framework/storage changes. The recovered storage
lines improve the measurement; the 35% gate, scope and exclusions are unchanged.

The synthetic data rehearsal preserves existing player/user/task-result values
across the three upstream task-result migrations. A clean checkout passes the
coverage suite and XML export. See [upgrade checkpoints](django-upgrade-checkpoints.md)
for deployment instructions and the follow-up on the documented but not yet
published 5.2.19 package. Hosted CI still needs verification after pushing.

## Follow-up: team-loader persistence

Nine new `upd_tms` integration cases bring the managed push-hook run to **445
passed**, with 12 external tests deselected and **83.20% combined coverage**.
`upd_tms` reaches 100% line/branch coverage. This is a focused regression checkpoint,
not proof that all possible team-report failures are handled.

The tests use real PostgreSQL saves and temporary media, with mocked schedule
responses and logo downloads. They protect creation/replay without duplicate teams
or repeated downloads, stable IDs/slugs/player/game links, preservation of historical
and unreported fields, attaching cached logos, replacing deleted logos, failure
before any team writes, and recovery after optional HTTP/URL logo failures.
Existing helper unit tests remain in place; the ORM is not mocked in this batch.

Application code, dependencies, coverage scope/exclusions and the 35% gate are
unchanged. The application database and live NHL endpoints were not accessed.
Malformed reports, non-connection HTTP failures and cross-team atomicity remain
separate loader-hardening decisions. Django 5.2.19 is still a pending patch task:
its PyPI metadata/download returned unavailable when rechecked for this batch.

## Follow-up: paginated player publication

Eleven additional integration cases bring the full managed push-hook run to
**456 passed**, with 12 external tests deselected and **83.57% combined coverage**.
The existing shared report fixtures now also run through mocked HTTP responses,
real pagination, report assembly and real PostgreSQL publication.

The cases cover successful skater/goalie publication and exact replay, draft
metadata, preserved history, duplicate/missing bios, conflicting games/summary/
enrichment rows, bounded retries and rejection of malformed/truncated/overflowing
later bios pages. All report callbacks observe unchanged saved players until
publication. Rejected reports preserve the full saved roster, and a bio without
summary statistics retains its existing values and season marker.

The ORM is not mocked. No live NHL calls, media writes or application-database
access are needed. Existing report/persistence tests remain; application code,
dependencies, migrations, coverage exclusions and the 35% gate are unchanged.


## Follow-up: totals refresh precedence and history preservation

Sixteen new integration cases, together with the intervening overtime-TOI and
historical-team fixes, bring the full offline run to **488 passed**, with
12 external tests deselected and **84.13% combined coverage**. The unchanged
35% gate, Ruff checks and formatting checks pass on Python 3.12.16 / Django 5.2.18
using a disposable PostgreSQL 16 cluster.

Shared synthetic reports exercise both skaters and goalies through real saves.
The cases check player/current-totals command ordering without landing calls,
replacement of overlapping historical seasons, preservation of unreturned history,
repeat refreshes without duplicate season/team rows, retained traded-player splits,
and historical-only backfills that leave the newer snapshot intact. Report data
wins over conflicting landing season totals. Career totals remain separate.

Injected report, career-fetch and database-save exceptions leave the saved player
unchanged. These are per-player preservation contracts, not whole-command rollback:
the totals command saves players individually. The ORM is used for persistence;
upstream reports/enrichment and selected failure points are mocked. No application
database or live NHL endpoints were accessed. Application code, dependencies,
migrations and coverage exclusions are unchanged.


## Follow-up: read-only saved-game TOI audit

The `audit_game_toi` command adds 28 integration cases. The full offline suite
passes **516 tests**, with 12 external tests deselected and **84.78% combined
coverage**, on disposable PostgreSQL 16. Ruff and formatting checks pass; the
35% coverage gate and coverage exclusions are unchanged.

Tests use real saved games/players and mocked NHL responses, including overtime
shift rows, shared jerseys, boxscore precedence, genuine zero TOI, mismatches,
missing saved data, missing/partial reports, HTTP/JSON failures, wrong source
identity/date, non-final games, selection bounds and continuation after a failed
game. SQL captured during a successful audit contains only SELECTs and the
PostgreSQL SELECT cursor declaration; saved game/day/player snapshots stay intact.

The command has no repair mode. No live NHL calls or application-database access
were performed during validation. Operational examples and the distinction between
mismatches, unverified evidence and zero selected games are in [game loading](game-loading.md).


## Follow-up: audit pacing, progress and resume

Twenty-one additional regression cases bring the offline suite to **537 passed**,
with 12 external tests deselected and **85.36% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% coverage gate pass.

The audit now defaults to locally finished games, paces every HTTP request, honors
numeric/HTTP-date Retry-After, applies bounded rate-limit backoff and stops on
persistent throttling. Progress goes to stderr; optional JSONL checkpoints flush
per game and support resuming without refetching verified games. Unverified games
are retried; latest results replace previous findings in the final summary.

Tests exercise selection opt-in, stdout/progress separation, request pacing,
report/JSON rate limits, long cooldowns, interruption and incremental durability,
resume/retry/deduplication, partial-line recovery, corrupt-file rejection and
protection against overwriting files or mixing selections. All HTTP responses and
waits are mocked; application data and live NHL endpoints were not accessed. The
command still performs no database writes and has no repair mode.


## Follow-up: targeted PP/SH gamelog repair

Fourteen additional integration cases bring the full offline suite to **551 passed**,
with 12 external tests deselected and **85.67% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% gate pass.

The audit remains read-only by default. Explicit `--repair` re-fetches sources and
patches only verified PP/SH mismatches under per-game transactions and row locks.
Tests cover skaters/goalies, verified zeroes, unverified-field preservation, exact
preservation of all other saved columns/gamelog content, roster/favorite retention,
clean re-audits and idempotence. Simulated concurrent field/identity/date changes
are checked again before saving; unrelated edits survive, already-correct values
are recognized and duplicate evidence is refused.

Injected database failures roll back all patches for the current game while
preserving earlier committed games. Rate limits prevent partial-game patches.
Repair checkpoints are mode-specific, retry conflicts/failed games, and never
reuse old read-only findings to perform writes. All HTTP responses are mocked.
No live repair or application-database write was performed during validation.


## Follow-up: rostered skaters with zero ice time

Nine new integration cases bring the offline suite to **560 passed**, with
12 external tests deselected and **85.68% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% coverage gate pass.

When a rostered skater's boxscore explicitly reports valid zero total TOI, missing
report PP/SH fields can be verified as zero. Missing, invalid or positive total
TOI remains insufficient evidence. Tests cover equivalent zero time formats,
unchanged saved records during audit, unavailable report blocks, rejection of
unknown/invalid totals, and targeted repair of wrong/missing saved values using
zero-total evidence. All NHL responses are mocked; no live audit or application
writes were performed. User-reported zero total TOI for Zachary L'Heureux explains
the prior two unverified fields; re-run the live single-game audit to confirm.


## Follow-up: player biography and flag persistence

Twenty new integration cases bring the full offline suite to **580 passed**, with
12 external tests deselected and **86.07% combined coverage** on disposable
PostgreSQL 16. `upd_pls` reaches 95% combined coverage. Ruff, formatting and the
unchanged 35% coverage gate pass.

Shared synthetic season reports run through mocked HTTP, real command publication
and PostgreSQL saves for both skaters and goalies. Tests cover biography/position/
team refreshes, stable primary keys/slugs and saved memberships, preserved gamelogs
and unreported metadata, distinct nationality/birth countries, nationality fallback,
birthday boundaries, retained draft history and later explicit corrections.
Current roster changes do not relabel a player's saved season contribution.

Temporary media exercises the real flag lookup/attachment code: cached flags attach
once, follow nationality changes and remain local; missing flags do not block stats
publication and recover when their files become available. Unknown country codes
persist and warn once per command, with a summary warning. HTTP inputs are mocked
and unexpected urllib downloads fail the tests. Application code, dependencies,
migrations, coverage scope and the gate are unchanged. No application data or live
NHL endpoints were accessed. Career-enrichment response handling remains a separate
regression/hardening batch.


## Follow-up: HTTP-backed career enrichment

Twenty-four integration cases bring the offline suite to **604 passed**, with
12 external tests deselected and **87.53% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% coverage gate pass.

Synthetic aggregate HTTP responses pass through real request helpers and real
current/full command saves for skaters and goalies. Tests check player/regular-season
query scope, aggregate flags, limits and timeout, unchanged records during fetching,
replay, separate season/history data, skater total/average precedence, goalie
aggregate replacement, full-mode landing precedence and derived goalie saves.
Partial rows and valid zeroes retain their distinction from unknown values.

Empty responses, HTTP 503/429 and timeouts preserve saved optional career values;
the existing no-retry policy is unchanged. Invalid JSON, non-object payloads,
missing/null data lists and non-object rows now raise contextual CommandError
rather than resembling empty reports or leaking shape errors. The malformed-input
cases verify that the current player's staged season/career data remains unsaved.
This is structural validation, not proof of numeric validity, aggregate completeness
or whole-command rollback. No live NHL calls or application data were accessed.


## Follow-up: rendered player profiles and gamelogs

Twenty-four integration cases bring the offline suite to **628 passed**, with
12 external tests deselected and **87.91% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% coverage gate pass.

Existing synthetic player/season fixtures and the rendered-table parser are reused.
The cases assert actual skater/goalie career rows, totals, averages and rate
formatting; current-panel visibility for stale/missing season markers and zero
games; newest-first recent/full gamelogs; PP/SH time rendering; the 25/26-game pager
boundary; empty histories; and profile/gamelog links. Saved data stays unchanged
by the tested GET workflows. Projection timing is frozen and live HTTP is blocked.
The profile still has no season selector; a query parameter does not rewrite its
career history or change its current-panel selection.

Four identity tests initially exposed server errors for missing IDs and mismatched
slugs. Both player views now raise Http404 when their lookup returns no player.
The shared lookup and other endpoints are unchanged. No application database or
live NHL endpoints were accessed. Game-detail/navigation and user-owned actions
remain separate regression batches.


## Follow-up: game detail and scoreboard navigation

Sixteen integration cases bring the offline suite to **644 passed**, with
12 external tests deselected and **88.02% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% gate pass.

Existing saved-game fixtures, mocked loader inputs and the rendered-table parser
protect all four skater groups and both goalie tables. The checks distinguish
selected-date gamelog values from season snapshots and other dates, including
PP/SH times and goalie rates/results; verify player links, last-name ordering,
viewer-specific favorites and missing-log/empty-roster behavior; and assert that
rendering makes no extra HTTP calls.

Scoreboard tests cover six-day windows at both ends and in the middle, selected
score/game/date links, empty databases, valid unavailable dates and invalid dates.
Six initially failing cases exposed missing game 404s, malformed-date server
errors, an import-time default date and fallback ordering by insertion rather than
calendar date. Views now return 404 for invalid game identities/dates, evaluate the
Pacific default date per request and choose the latest calendar day as fallback.
No migrations, application data or live NHL endpoints were involved. Search and
user-owned action gaps remain the next focused batches.


## Follow-up: search and autocomplete input contracts

Twenty-two integration cases bring the offline suite to **666 passed**, with
12 external tests deselected and **89.11% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% coverage gate pass.

Shared isolated view fixtures protect mixed skater/goalie/team matching,
case-insensitive trimmed queries, literal percent/underscore/Unicode terms, empty
results, profile/team links, suggestion grouping/separators and viewer-specific
favorite/comparison controls. Blank search/autocomplete requests perform no model
reads. An HTML parser checks autocomplete labels and URL parsing checks that
reserved query characters round-trip without becoming attributes or fragments.

Eleven initially failing cases exposed whitespace searches returning all records,
blank autocomplete suggestions, noncanonical detail links and raw HTML/query
construction. Views now trim before searching, return no suggestions for blank
terms, reverse canonical internal routes, escape labels with format_html and
encode full-results queries. Literal substring matching and the existing JSON
shape/grouping remain. All tests block live HTTP and use isolated PostgreSQL;
no application data or schema changes were involved. Interactive browser behavior
and user-owned mutation endpoints remain separate batches.


## Follow-up: private notes and extra positions

Twenty integration cases bring the offline suite to **686 passed**, with
12 external tests deselected and **90.00% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% coverage gate pass.

Tests use colliding skater/goalie primary keys and two users to protect typed
ownership, forged-ID resistance, repeated updates/clears, note-length validation,
allowed position choices, missing-player 404s, anonymous no-write behavior, CSRF
and escaped private note rendering. Legacy untyped rows are retained when ambiguous
and read/upgraded on edit only when unambiguous. See [compatibility details](private-player-data.md).

Endpoints and profile lookups now include player content type. Positions validate
the actual submitted checkboxes and notes/positions report form errors with HTTP
400 instead of claiming success. No schema migration, bulk reassignment, live HTTP
or application-database access was involved. Concurrency/uniqueness constraints
and ambiguous legacy-data review remain separate work.


## Follow-up: saved measurement preferences

Twenty-two integration cases bring the offline suite to **708 passed**, with
12 external tests deselected and **90.05% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% gate pass. No application
changes were needed.

Existing isolated users/player-season fixtures drive real profile POSTs, rendered
player detail pages and all three Players AJAX table modes. Tests cover USA/Europe
updates and replay, forged profile/user identifiers, other-account isolation,
invalid/blank/missing choices preserving both account and profile values, login
redirects and CSRF. Invalid choices re-render the browser form with errors (HTTP
200), consistent with the existing profile workflow.

Anonymous/default and signed-in profile displays, table height/weight values and
height options follow the chosen units. Switching viewers/preferences repeatedly
does not leak settings or accumulate conversion drift. Full saved player snapshots
remain unchanged by display conversion. All HTTP is blocked, media paths are
temporary, and the application database was not accessed. Existing upload and
metric-filter cases remain; this batch does not claim transaction rollback for
runtime save failures or interactive browser coverage.


## Follow-up: favorites/comparison mutation and quota boundaries

Sixteen integration cases bring the offline suite to **724 passed**, with
12 external tests deselected and **90.13% combined coverage** on disposable
PostgreSQL 16. Ruff, formatting and the unchanged 35% gate pass.

Tests use the real 100-player shared favorites quota and separate five-player
skater/goalie comparison quotas with real M2M writes. They protect the final allowed
addition, rejection at capacity, removal while full and adding after removal;
independent comparison groups; other-user/favorite preservation; repeated toggles
without duplicate memberships or player-column changes; anonymous POST no-writes;
and repeated comparison resets affecting only the selected user/group.

Four initially failing target-identity cases exposed server errors for missing IDs
and mismatched slugs. Favorite/comparison endpoints now raise Http404 when lookup
fails, leaving saved lists unchanged. Toggle semantics, quotas, HTTP methods and
selection payloads are unchanged. These are sequential contracts, not concurrent
quota enforcement; GET-to-POST/CSRF migration is separate work. HTTP is mocked and
the application database was not accessed.


## Follow-up: Chromium smoke-test foundation

The offline gate passes **725 tests**, with 12 external and 3 browser cases
deselected, at **90.13% combined coverage** on disposable PostgreSQL 16. The
additional offline case validates the browser runner's isolated settings/selection.
All **3 Chromium checks** also pass through the dedicated local runner, using Node
24 and the locked Playwright package. Ruff, JavaScript syntax, workflow actionlint
and the unchanged 35% gate pass; cached assets and locked npm dependencies were
also prepared successfully without network access after initial installation.

Browser checks exercise real season submission, totals/averages/goalie controls,
selected-season AJAX requests and unloaded-season empty states. Checksum-pinned
copies of existing CDN assets run the real frontend code with external network
requests blocked. The cases initially exposed jQuery UI failures from empty
nationality checkbox options; empty metadata options are now omitted rather than
rendering controls with no usable label. Screenshots/traces are captured on failure.

Node/Chromium setup is optional locally and separate from Python dependencies,
normal hooks and server-side coverage. CI is configured to run both suites and
upload browser failures; hosted execution is not yet verified. No application data
or live NHL API was used. Saved-list/team browser workflows remain follow-up work.


## Follow-up: authenticated saved-list browser controls

All **7 Chromium cases** pass through the dedicated isolated runner: the existing
three Players checks plus four authenticated saved-list scenarios. The offline gate
still passes **725 tests**, with 12 external and 7 browser cases deselected, at
**90.13% combined coverage**. Ruff, JavaScript syntax and formatting checks pass.

Shared real-browser/network/trace infrastructure and synthetic Django sessions
exercise goalie-only/empty favorites, old-season unavailability, totals/averages,
comparison season/career modes and season-preserving removal/reset interactions.
Post-browser PostgreSQL checks confirm only intended owner comparison memberships
change; other users' saved lists, favorites and stored player columns stay intact.
Favorites gamelogs remain independent of season selection.

The goalie-only scenario exposed an unavailable-season status present in JSON but
missing from the DOM because it followed a closed legacy table cell. The affected
favorite name/status cell now uses valid escaped HTML fragments with canonical
profile links. No dependency, schema, application-data or workflow changes were
needed; the existing CI browser selection automatically includes the new cases.
Hosted execution still needs confirmation after pushing. Team browser controls
and remaining favorites mutations are separate follow-ups.


## Follow-up: team layout browser controls

All **10 Chromium cases** pass through the dedicated isolated runner, including
three new team scenarios. The offline gate remains **725 passed**, with 12 external
and 10 browser cases deselected, at **90.13% combined coverage**. Ruff, formatting
and browser-script syntax checks pass; no application-code changes were needed.

Existing traded-player/season fixtures exercise independent defence/forward
averages, joined totals/averages, re-splitting into both groups without duplicate
visible rows, historical-season submission and unloaded-season states. Actual team
contributions and goalie values must remain distinct from overall totals and
conflicting snapshot fields. All team AJAX requests retain the selected season,
and full team/skater/goalie database snapshots remain unchanged after interaction.

The existing offline asset/browser harness and CI selection include these cases
without new dependencies or setup. No live NHL calls or application data were used.
Favorites mutations and browser-level AJAX failure/recovery remain separate work.


## Follow-up: favorites removal and empty-state browser transitions

All **14 Chromium cases** pass through the isolated runner, including four new
removal cases (last member of either group and final favorite of either type).
The offline gate remains **725 passed**, with 12 external and 14 browser cases
deselected, at **90.13% combined coverage**. Ruff, formatting and JavaScript syntax
checks pass.

The four cases initially failed. The favorites template left group wrappers
unclosed and offered the empty state only at initial render; the removal handler
did not hide empty groups or activate the remaining group. The wrappers are now
independent, a persistent empty-state container is toggled from server counts,
and the controller updates both counts, preserves season parameters and refreshes
the current page when a group remains. Messages use text, requests are guarded
while in flight, and failed/unconfirmed responses leave visible records intact.

Real keyboard link activation exercises the mutation endpoint; reloads confirm
persistence. Database checks protect other users' favorites, both users' comparison
lists and all stored player columns. The existing offline assets and CI browser
selection include these cases without new dependencies. No application data or
live NHL calls were involved. Legacy GET/toggle semantics, concurrent mutations
and browser-level failure injection remain separate work.

## Follow-up: browser AJAX failure and recovery

All **17 Chromium cases** pass through the isolated browser runner. Three new
cases inject six one-shot HTTP 503 failures: favorites removal, comparison mode/
removal/reset, and team mode/split-layout changes. Existing data, counts and modes
survive failures; errors are visible, controls permit explicit retries, and real
successful responses clear errors and publish the expected values. Partial failure
of the two-request team split preserves the joined layout until a successful retry.

Only exact injected requests are exempt from the harness HTTP-error check.
Unexpected AJAX errors and JavaScript exceptions still fail. Synthetic-user
membership assertions protect other users and unrelated saved lists; complete
player/team snapshots remain unchanged. Failures are injected before Django, so
these tests do not claim safe retries after a committed mutation loses its response.
No application behavior or dependencies changed.

The offline gate passes **725 tests**, with **29 deselected** (12 external and
17 browser), at **90.13% combined line/branch coverage**, retaining the 35% gate.
Ruff, formatting, JavaScript syntax and whitespace checks pass. Both suites use
disposable PostgreSQL clusters; no application database or live NHL calls are used.

## Follow-up: filtered and paginated favorites removal

All **21 Chromium cases** pass. Four new cases cover skaters and goalies with
26 synthetic favorites: remove the sole name-filter match without hiding the
remaining favorites, or remove the only row on page two and return to page one.
Filters, ascending name sorting, selected season and global counts survive
removal. The no-match message clears after removing the filter, and the pager
hides when only one page remains. Fresh renders confirm deletion persists;
filters are explicitly reapplied after reload rather than assumed persistent.

Other users' memberships, the owner's opposite-type favorites and comparison
lists, and all stored player columns remain unchanged. The existing controller
passes these regressions without application changes or new dependencies.

The offline coverage gate remains **725 passed**, with **33 deselected**
(12 external and 21 browser), at **90.13% combined coverage** against the 35% gate.
Ruff, formatting, JavaScript syntax and whitespace checks pass. Validation uses
disposable PostgreSQL clusters and real Chromium with cached assets; no
application database or live NHL services are involved.

## Follow-up: shared table-cell escaping and display contracts

The offline gate passes **744 tests**, with **33 deselected** (12 external and
21 browser), at **90.24% combined line/branch coverage**, retaining the 35% gate.
All **21 Chromium cases** pass. Ruff, formatting and whitespace checks pass.

Thirteen unit cases and six database-backed AJAX cases cover literal player names,
team/nationality/opponent tooltips, balanced links/cells, escaped URL attributes,
goalie precision, numeric zeros, missing statistics and missing draft/team metadata.
Real Players and favorites-gamelog responses retain literal text and leave stored
records unchanged. Fixtures use disposable PostgreSQL; no application data or NHL
services are accessed.

The initial focused run exposed unclosed player anchors, raw HTML interpolation
in names/tooltips and a missing-save-percentage formatting crash. Shared helpers
now use Django's escaped HTML formatting and close anchors explicitly. Gamelogs
retain the missing-value dash instead of passing it to numeric formatting;
reported zeros still format as `0.000`. Existing Chromium checks validate the
resulting markup through the real tablesorter UI. Other model/template rules,
checkbox rendering and legacy mutation design remain separate focused work.

## Follow-up: filter-checkbox escaping and selection contracts

The offline coverage gate passes **767 tests**, with **33 deselected** (12 external
and 21 browser), at **90.26% combined line/branch coverage**, retaining the 35% gate.
All **21 Chromium cases** pass; Ruff, formatting and whitespace checks pass.

Seventeen unit cases cover literal checkbox labels, tooltip text and attributes,
checked/unchecked options, empty selections, option-list preservation and wrapping
after eight options. Six database-backed AJAX cases cover team/country/position
filters in totals and averages. They read the decoded value from rendered HTML,
select it through the real endpoint, confirm checked state and matching rows,
then clear it and confirm the full result set returns. Stored records remain
unchanged; synthetic fixtures use disposable PostgreSQL and no live NHL services.

Checkbox labels, tooltips, values, IDs and classes now use escaped HTML formatting,
preserving the existing markup for ordinary values. The wrapper computes checked
state for every option, including explicit empty/None selections that previously
could leave `check_this` unset and raise an error. No dependencies, migrations or
application data changed.

## Follow-up: malformed game-roster publication guards

The offline gate passes **811 tests**, with **33 deselected** (12 external and
21 browser), at **90.46% combined line/branch coverage**, retaining the 35% gate.
Ruff, formatting and whitespace checks pass. Browser cases were not rerun for
this loader-only change.

Forty-four database cases reuse the synthetic game/report fixture. Twenty defect
shapes are tested on both fresh and existing days: malformed roots/sides/groups,
non-object entries, missing/invalid IDs or positions, duplicate identities,
missing goalie participation fields and wholly empty sides. Full snapshots protect
saved games, sides, players, completion flags, roster links and saved memberships.
The original loader failed 41 of the 44 cases.

Supplied rosters now validate before supplemental report fetching and database
updates. Shape failures raise contextual `CommandError` with date, game ID,
boxscore URL and invalid path. Numeric-string IDs retain compatibility; duplicate
IDs cannot silently collapse M2M roster counts. No fixed roster size is assumed.

A later malformed game rolls back earlier writes on the same day. After correcting
the response, the same two-game schedule replays twice with stable IDs, unchanged
older history/memberships and completed flags. Unavailable rosters remain pending
without erasing previous links/logs, and nested legacy rosters remain supported.
Validation uses disposable PostgreSQL and mocked HTTP; no application database or
live NHL calls are involved. Changed-participant/gamelog cleanup is the remaining
planned testing commit for this phase.

## Follow-up: changed participants and verified gamelog cleanup

The offline gate passes **849 tests**, with **33 deselected** (12 external and
21 browser), at **90.55% combined line/branch coverage**, retaining the 35% gate.
Ruff, formatting and whitespace checks pass. Browser cases were not rerun for
this loader-only change.

Thirty-eight new database cases protect removal/replacement across all six roster
groups with tagged and legacy entries, goalie bench corrections, position/side
changes, typed skater/goalie IDs, missing replacement players, repeated reloads
and rollback after cleanup. The first 33 cases all failed against the prior loader.
Older history, unrelated player fields and favorites/comparison memberships stay
intact; a later malformed game restores removed gamelogs and roster links.

Newly loaded date entries include `gameId`. Cleanup considers only previous roster
members absent from the refreshed played roster and verifies both game and player
identity. Legacy entries require matching player/team/opponent metadata and no
other same-date game appearance. Conflicting or malformed entries are retained
with a warning; roster links still reconcile to the supplied response. No schema
migration, automatic historical sweep or live NHL calls are involved. Fixtures use
disposable PostgreSQL; application data is untouched.

This completes the agreed testing phase. Hosted CI/dependency-graph verification
and deployment/migration rehearsal on a disposable representative database copy
are next; optional edge cases remain separate work rather than extending this phase.

## Follow-up: bounded HTTP retries across supported loaders

The offline gate passes **893 tests**, with **33 deselected** (12 external and
21 browser), at **90.86% combined line/branch coverage**, retaining the 35% gate.
Ruff, formatting and whitespace checks pass. Browser cases were not rerun for
this loader-only change. No live NHL requests or application database writes were
performed; persistence validation uses a disposable PostgreSQL cluster.

Forty-four new unit cases protect seconds/date cooldowns, invalid/past/large
headers, exponential waits, bounded exhaustion, permanent HTTP errors, transport
recovery, resource cleanup, sessions/parameters, one combined HTTP/JSON attempt
budget and recovery through eleven loader request paths. The shared helper uses
three attempts and refuses retry waits over sixty seconds instead of retrying
earlier than the server requested. Offline tests mock clocks/waits; external checks
retain actual waits.

Teams, player/season reports, landing/career requests, game JSON/HTML, projection
requests and image downloads use this policy. Required failures retain command
errors and existing publication/rollback boundaries. Optional non-rate-limit
failures retain fallbacks; exhausted 429 stops even optional career/image/HTML
fetches and season detection. Updated real-database regressions verify the current
player stays unchanged on rate-limit failure, existing career data survives other
optional failures and logos retain cache/replay behavior. Archived experiments and
the audit's separate pacing/checkpoint policy remain outside this refactor.

## Follow-up: HTTP/TLS dependency security checkpoint

Four requirements pins change: certifi **2025.6.15 → 2026.10.18**, Requests
**2.32.4 → 2.33.0**, urllib3 **2.5.0 → 2.8.0**, and idna **3.10 → 3.15**.
Official PyPI metadata confirms availability, non-yanked artifacts and compatible
Python requirements for the project's Python 3.12.16 checkpoint. These are the
minimum fixed releases covering the current affected ranges of repository alerts
**#47, #48, #49, #52, #80, #81, #105, #140 and #158**. No alerts were dismissed;
GitHub must rescan the updated default branch after push.

A fresh temporary venv installs the unchanged bootstrap requirements and complete
updated requirements successfully, with `pip check` reporting no broken requirements.
In that environment, **893 offline tests** pass at **90.86% combined line/branch
coverage** with **33 deselected**, and all **21 Chromium tests** pass with
**905 deselected**. Ruff, formatting and whitespace checks pass. Both suites use
disposable PostgreSQL; application data and live NHL services are not accessed.

The loaded certifi trust store contains none of the removed emSign roots and
Requests selects that bundle. An independent local HTTPS check rejects an
untrusted self-signed certificate and succeeds when its certificate is explicitly
trusted; TLS verification is enabled throughout. IDNA encoding also passes.
The existing project venv was left unchanged: install `requirements.txt` and restart
running application processes to use the patched packages. No application code,
bootstrap pins, other dependency pins or uv files changed.

## Follow-up: Pillow security and image-upload compatibility

Pillow changes from **10.4.0 to 13.0.0**. Official metadata confirms non-yanked
artifacts, Python **>=3.11** support and a compatible CPython 3.12 Linux wheel.
The new pin falls outside the affected ranges of all **52 currently open Pillow
alerts**, including **#154 / GHSA-5x8w-8jj5-q52h** (critical FPX/JPEG decoding).
No alerts were dismissed or modified; closure awaits push and GitHub rescanning.

A clean temporary Python 3.12.16 venv installs the complete pinned requirements
and passes `pip check`. **902 offline tests** pass with **33 deselected** at
**90.86% combined line/branch coverage**, retaining the 35% gate. All **21 Chromium
cases** pass with **914 deselected**. Ruff, formatting and whitespace checks pass.
Validation uses disposable PostgreSQL and temporary media; no application data or
live NHL services are accessed. The active project venv was left unchanged.

The existing two upload tests expand to eleven cases (nine additional cases).
Valid PNG, JPEG and WebP uploads retain their format, dimensions and encoded bytes;
PNG pixels also retain exact values. Corrupt data, SVG disguised as PNG, truncated
PNG and a generated image exceeding a temporarily lowered Pillow pixel threshold
are rejected through the real profile form. Tests cover both a default avatar and
an existing stored image, protecting file bytes, image references, email and
measurement preferences on rejection. The normal pixel threshold is not changed.

Application image-handling code, accepted-format policy, bootstrap/dependency pins
other than Pillow and uv configuration are unchanged. Install requirements and
restart running app processes to activate the patched dependency.

## Follow-up: remove the unused MySQL startup shim and driver

Repository searches found PyMySQL only in requirements and the startup shim;
application/test settings and CI use PostgreSQL with `psycopg2-binary`. The
`pymysql` import and `install_as_MySQLdb()` call are removed from package startup,
and `PyMySQL==0.9.3` is removed from requirements. The Celery app import/export is
preserved. This removes the dependency responsible for **#15 /
GHSA-v9hf-5j83-6xpp**; no MySQL query callers or database migration changes were
found. Alert closure awaits default-branch push and GitHub rescanning.

A fresh temporary Python 3.12.16 environment installs the complete pinned
requirements and passes `pip check`, with neither `pymysql` nor `MySQLdb`
importable and PostgreSQL's adapter available. Against disposable PostgreSQL,
`check --database default` reports no issues and `makemigrations --check --dry-run`
reports no changes. **902 offline tests** pass at **90.86% combined line/branch
coverage**, with **33 deselected**; all **21 Chromium cases** pass with
**914 deselected**. Ruff, formatting and whitespace checks pass.

The existing clean-checkout startup case now forbids MySQL-driver imports while
initializing Django twice, the WSGI application, the native PostgreSQL backend
and the same exported Celery app, without any database or HTTP connection. Existing
Celery task-order/result and real PostgreSQL persistence regressions also pass.
Application databases and live NHL services were not accessed. The project venv
was left unchanged: explicitly uninstall PyMySQL after applying the code change
and restart running app/worker processes; `pip install -r requirements.txt` alone
does not remove an already-installed unused package.

## Follow-up: sqlparse and tqdm security checkpoint

Two requirements pins change: **sqlparse 0.5.3 → 0.6.1** and **tqdm 4.36.1 →
4.70.1**. Official metadata confirms published, non-yanked releases compatible
with Python 3.12.16. The new pins fall outside the current affected ranges for
**#12, #50, #100, #101, #102, #103 and #104**. sqlparse 0.6.1 is chosen over 0.6.0
because upstream documents additional PHP-output escaping and regex DoS fixes.
The maintainer announced that 0.6.1 is the final maintained release; this is recorded
as a separate dependency risk to track with Django's guidance, not a reason to
retain the older vulnerable pin. Django's metadata still requires sqlparse.

A fresh temporary environment installs the complete bootstrap/project requirements
and passes `pip check`. Against disposable PostgreSQL, system checks report no
issues and migration consistency checks report no changes. **902 offline tests**
pass at **90.86% combined line/branch coverage**, with **33 deselected**, and all
**21 Chromium cases** pass with **914 deselected**. Ruff, formatting and whitespace
checks pass. Application data and live NHL services are untouched.

Separate temporary smoke checks exercise sqlparse splitting/formatting of quoted
and dollar-quoted semicolons with comments, tqdm iterable/progress output and CLI
stdin/stdout streaming. The CLI rejects `--buf-size=1+1` rather than evaluating it.
No application behavior, schema, permanent tests, other package pins or uv files
change. The existing project venv is unchanged; reinstall requirements and restart
running app/worker processes. Alert closure awaits default-branch push/rescanning;
no alerts were dismissed or modified.

## Follow-up: uv metadata and lockfile foundation

Add `[project]` metadata with the validated Python 3.12 minor range, runtime
dependencies and `test`, `hooks` and default `dev` groups. Preserve all **64 unique
pins** from the three existing requirements files exactly; no dependency upgrades
or removals are part of this checkpoint. Keep the checkout application unbuilt
with `package = false`; retain Ruff settings. Isolated dependency builds constrain
setuptools/wheel/packaging to the bootstrap versions. Add `uv.lock` from public
PyPI with transitive dependencies, platform markers and artifact hashes, and ignore
the default `.venv/` directory. See the [migration checkpoint](uv-migration.md).

Validated with **uv 0.10.10 / Python 3.12.16**. `uv lock --check --offline` passes.
Clean `uv sync --locked` installs **74 distributions** with no version differences
from the validated pip environment; a separate `--no-default-groups` environment
installs **45 distributions** without pytest, hooks or lint tools. Both dependency
checks and offline `uv sync --locked --check` runs pass. Runtime-only system/
migration checks and WSGI/Celery startup pass against disposable PostgreSQL 16.
The default environment passes system/migration checks, **902 offline tests**
(**33 deselected**) at **90.86% combined coverage** with the unchanged 35% gate,
and **21 Chromium tests** (**914 deselected**), without warnings. Ruff, formatting
and whitespace checks pass. uv normalizes malformed version specifiers while
reading older candidate metadata during initial resolution; locking and isolated
source builds complete successfully without package-version changes.

The existing project venv, requirements files, Make targets, hook runner and CI
are unchanged. Tests explicitly select temporary uv interpreters because the
current runner still prefers the existing project venv. Application data and live
NHL services are untouched. No application code, schema, permanent tests or browser
dependencies change. The next commit switches workflows and interpreter selection;
uv installation/provisioning and hosted CI validation remain for that step.

## Follow-up: requests-mock plugin deprecation cleanup

Update **requests-mock 1.8.0 → 1.12.1**, a published, non-yanked release compatible
with Python 3.12 and Requests 2.33.0. The plugin now compares numeric version tuples
instead of using `distutils.version.StrictVersion`, removing the three warnings
surfaced by pytest 9.2. No warnings are suppressed and no test fixtures change.

The disposable pytest validation environment installs the updated requirements
and passes `pip check`. A separate Python process imports the plugin with
`DeprecationWarning` treated as an error. Against disposable PostgreSQL 16,
Django system checks pass and migration checks report no changes. **902 offline
tests pass**, with **33 deselected**, at **90.86% combined coverage**, retaining
the 35% gate. All **21 Chromium tests pass**, with **914 deselected**. Neither
suite reports warnings. Ruff, formatting and whitespace checks pass.

The existing project venv remains unchanged; install updated requirements to use
the new plugin. Application data and live NHL services are untouched. No app code,
schema, test selection, hook/CI commands, warning filters or uv files change.

## Follow-up: packaging tools security checkpoint

Bootstrap pins change from **pip 24.0 → 26.3**, **setuptools 75.8.0 → 84.2.1**
and **wheel 0.42.0 → 0.48.0**. PyPI metadata confirms published, non-yanked
releases compatible with Python 3.12.16. Their versions fall outside all ten
current affected ranges: **#142–#151**. Wheel 0.48.0 also includes an additional
`wheel convert` path-traversal fix beyond the minimum version in alert #144;
see the [upstream release notes](https://wheel.readthedocs.io/en/stable/news.html).
Wheel now requires `packaging>=24.0`; **packaging 23.2 → 26.3** is therefore
pinned consistently in bootstrap and project requirements.

A fresh temporary venv installs bootstrap, full project and hook requirements,
then passes `pip check` and pre-commit configuration validation. Temporary smoke
checks build a synthetic local package using the installed setuptools backend,
unpack its wheel, install it without an index, import it and uninstall it.
Uncached source builds of MarkupSafe 1.1.1, docopt 0.6.2 and django-shortcuts 1.6
also pass using the patched tools with build isolation disabled, establishing
compatibility beyond previously cached wheels.

Against disposable PostgreSQL 16, Django system checks report no issues and
migration consistency checks report no changes. **902 offline tests pass**, with
**33 deselected**, at **90.86% combined line/branch coverage**; the gate remains
35%. All **21 Chromium tests pass**, with **914 deselected**. Ruff, format and
whitespace checks pass. Application databases and live NHL services are untouched.
No application code, migrations, permanent tests, CI commands or uv files change.
The existing project venv remains unchanged; install bootstrap requirements before
project/hook requirements as documented in [testing](testing.md#python-environment).
Alert closure awaits default-branch push/rescanning; no alerts were dismissed.

## Follow-up: retire the unused documentation dependency chain

Remove 19 unused pins: Sphinx, alabaster, Babel, docutils, imagesize, Jinja2,
MarkupSafe, Pygments, snowballstemmer, the seven sphinxcontrib packages, pockets,
importlib-metadata and zipp. Repository callers and active dependency metadata on
Python 3.12 show no remaining need for this chain. The configured template backend
is DjangoTemplates. The separate Napoleon package duplicates the built-in Sphinx
extension, and the metadata backports have no active consumers on this interpreter.
Remove the obsolete `docs/conf.py`, `docs/index.rst` and `docs/Makefile`: their
machine-specific Python 3.6 paths and missing `modules` document do not provide a
working documentation build. All Markdown guides remain, linked from the README.

The removed pins account for eleven current alerts: **#1, #13, #18, #37, #39,
#53, #57, #58, #60, #64 and #71**. No alerts are dismissed; closure depends on
default-branch push/rescanning. The pytest alert is a separate compatibility task.

A fresh temporary Python 3.12.16 venv installs bootstrap, project and hook
requirements. All 19 removed distributions are confirmed absent, `pip check`
reports no broken requirements, and pre-commit configuration validation passes.
Against disposable PostgreSQL 16, Django system/migration checks pass with no
changes. **902 offline tests pass**, with **33 deselected**, retaining **90.86%
combined line/branch coverage** and the unchanged 35% gate. All **21 Chromium
tests pass**, with **914 deselected**. Ruff, formatting and whitespace checks pass.
No application data or live NHL services are accessed. No application code,
migrations, permanent tests, CI commands or uv files change. The project venv is
unchanged; [cleanup instructions](testing.md#python-environment) explain that
installing requirements alone does not uninstall the removed packages.

## Follow-up: pytest temporary-directory security fix

Update **pytest 7.4.4 → 9.2.0**, outside alert **#54**'s affected range `<9.0.3`.
The [upstream changelog](https://docs.pytest.org/en/stable/changelog.html#pytest-9-0-3)
records the insecure temporary-directory fix in 9.0.3. Official PyPI metadata
confirms the selected releases are published, non-yanked and Python 3.12-compatible.
Pytest requires `pluggy>=1.6,<2` and `pygments>=2.15`, so **Pluggy 1.3.0 → 1.7.0**
and **Pygments 2.21.0** are pinned alongside it. Pygments returns for pytest terminal
highlighting, not Sphinx; update the existing-venv cleanup instructions to retain it.
Existing pytest-cov 4.1.0, coverage 7.6.12, pytest-django 4.11.1 and requests-mock
1.8.0 remain unchanged after verifying compatibility.

A fresh temporary Python 3.12.16 environment installs bootstrap, project and hook
requirements and passes `pip check` plus pre-commit configuration validation.
Using disposable PostgreSQL 16, Django system checks pass and migration checks
report no changes. The normal commit-hook runner passes **902 tests**, with
**33 deselected**. The push-hook coverage runner also passes **902 tests**, with
**33 deselected**, retaining **90.86% combined line/branch coverage** and the 35%
gate. All **21 Chromium tests pass**, with **914 deselected**. Each run reports
three `distutils.version.StrictVersion` deprecation warnings from the existing
requests-mock plugin, now captured at plugin startup by pytest 9.2; no warnings
are suppressed. Updating that plugin is separate maintenance.

Ruff, formatting and whitespace checks pass. No application code, schema, test
selection, hook/CI commands or uv files change. Validation uses synthetic fixtures;
application data and live NHL services are untouched. The project venv is unchanged;
install updated requirements before using the existing hooks. Closing the final
currently open alert still requires a default-branch push and GitHub rescan;
no alerts were dismissed or modified.


## Follow-up: switch Make, hooks and CI to the locked uv workflow

Keep `pyproject.toml`, `uv.lock` and all resolved versions unchanged. Make commands
now use `uv run --locked`; new sync, lock-check and requirements generation/check
commands expose the locked workflow. Loader targets retain sequential execution,
stop-on-failure and intentional interpreter overrides; bare `make` still formats.
The standard-library test runner invokes uv directly instead of searching old or
active venvs. Local test hooks use system entries backed by uv and retain dedicated
credentials, selection isolation and exit propagation. Missing uv fails clearly;
stale locks and sync failures never fall back to an old interpreter.

CI pins uv 0.10.10 via setup-uv v10.3.3, caches by `uv.lock`, performs a locked sync,
checks dependencies/export drift, and runs existing checks and artifact exports
through uv. `requirements.txt` becomes a generated, hashed compatibility export;
the redundant bootstrap/hook requirement files are removed. Export failure leaves
the existing file intact. Current setup, loader, test and hook docs use uv; historical
upgrade checkpoint instructions are retained as history.

A fresh 74-package environment passes `make sync lock-check requirements-check
check` and dependency checks. With disposable PostgreSQL 16, actual Make-based
Django/migration checks, **902 offline tests** (**33 deselected**), **90.86% combined
coverage**, the unchanged 35% gate and coverage XML export pass. The actual Make
browser target passes all **21 Chromium tests** (**914 deselected**). Real commit
and push test hooks are installed and pass in a temporary Git checkout while a
legacy venv is marked active; the user's installed hooks and Git index are untouched.
The 14 hook-runner regressions also pass with no `python` command on PATH.

Separate temporary checks confirm stale locks block execution without changing the
lockfile, export drift is detected without overwriting files, and failed exports
preserve the previous file. Mocked Make loader checks verify order and failure
stopping under `-j4`, without invoking any NHL loader. Workflow/hook YAML, pinned
action inputs, shell syntax, Ruff/format, JavaScript and whitespace checks pass.
No application database, live NHL services, actual commit/push, application code,
schema or browser dependency changes are involved. The user's old venv is preserved;
run `make sync` and reinstall local launchers with `make hooks`. Hosted Actions
and Dependabot graph verification remain pending push.


## Follow-up: repair optional live NHL API contracts

Replace the 12 legacy external checks with **22 read-only contracts** for supported
loader sources. Retire exact ordered-key comparisons, old statsapi schedule/
boxscore/linescore contracts, the malformed legacy projection request assertion
and implicit hardcoded-current-season report calls. Keep the files marked both
`integration` and `external`, with no database fixtures or publication commands.
The legacy projection command itself is unchanged and flagged for the next audit.

Use completed regular season 2023–24, game 2023020001 / 2023-10-10 and representative
skater/goalie IDs through a lazy, shared session fixture. Request starts are paced
one second apart, including retries; the production HTTP helpers retain bounded
retries/timeouts and Retry-After behavior. Cover current team/calendar/registry,
schedule, boxscore/roster validation, both landing types, seven season report
combinations, four career report combinations, faceoff/TOI HTML parsers and
play-by-play PP/SH points. Event Summary is checked for a reachable report/table,
not nonexistent player PP/SH columns; those points come from play-by-play.

`make test-external` selects only these modules/markers, excludes browser tests
and stops on the first failure. Missing data and HTTP errors fail rather than
skip/xfail. Neither normal Make tests, hooks nor CI add live calls. Documentation
records references, scope, pacing and failure investigation.

The repaired Make live target passes **22 tests** against actual NHL sources.
Collection alone makes no HTTP requests. Normal offline collection selects **902
of 945 cases**, with **43 deselected** (22 external, 21 browser). The full offline
Make coverage workflow passes **902 tests**, **90.86% combined line/branch coverage**
and the unchanged 35% gate against disposable PostgreSQL 16. Django system/
migration checks and XML export pass. Ruff/format, requirements drift and whitespace
checks pass. Application records are untouched; only the explicit live validation
contacts NHL. No application code, schema, lockfile/dependency, hook or CI changes
are part of this batch. Live success is point-in-time availability/schema evidence,
not verification of all current-season players or production persistence.


## Follow-up: remove unused legacy lint tools

Remove only **mccabe 0.7.0**, **pycodestyle 2.9.1** and **pyflakes 2.5.0** from
`dev`, `uv.lock` and the generated requirements export. The audit found no tracked
callers or active mandatory dependents; Ruff remains the configured lint/format
entry point. Lock comparison confirms no additions or retained version changes.
A clean locked sync installs 71 packages, with all three removed tools absent,
and passes dependency, lock/export and Ruff/format checks. Against disposable
PostgreSQL 16, Django/migration checks, **902 offline tests** (**43 deselected**)
at **90.86% combined coverage**, the unchanged 35% gate and XML export pass.
All **21 Chromium cases pass** (**924 deselected**). Whitespace checks pass.
No application code, schema, loader, hook/CI behavior or other dependency changes;
no application data or live NHL calls. Run `make sync` in an existing uv environment
to prune the old tools; `uv run` alone may retain extraneous installed packages.


## Follow-up: remove obsolete test compatibility pins

Remove only **attrs 19.3.0**, **more-itertools 7.2.0**, **py 1.11.0** and
**pyparsing 2.4.2** from the test group, lockfile and generated export. Lock
comparison confirms no added packages or retained version changes. Explicitly
retain **django-shortcuts 1.6** for the user's confirmed command-line workflow.
A fresh locked environment installs 67 packages, with all four removed tools
absent, and passes dependency, lock/export and Ruff/format checks.

Against disposable PostgreSQL 16, Django system/migration checks, **902 offline
tests** (**43 deselected**) at **90.86% combined coverage**, the unchanged 35% gate
and XML export pass. All **21 Chromium tests pass** (**924 deselected**). Both
real commit/push test hooks pass in a temporary Git checkout with the old venv
marked active. A separate stub-manage.py smoke check confirms the installed
`django` CLI maps `r`/`m`/`mm` to runserver/migrate/makemigrations and uses the new
environment's interpreter; no real server or migration is started by that check.
No application code, schema, hook/CI behavior, other dependency versions, user Git
hooks or application data change; no live NHL calls. Run `make sync` to prune the
old packages from an existing uv environment. Whitespace checks pass.


## Follow-up: retire four top-level legacy commands

Remove upd_pls_proj, upd_vids, upd_pls_sbs-n and json_fixtures_creator after user
approval. Remove the projection import/parameter branch from the shared HTTP test;
remaining retry and supported-loader contracts stay intact. Five supported commands
remain discoverable. Make/Celery sequencing, models, profile rendering, dependency
metadata/lock/export, six old fixture exports and 22 OAuth-related JSON files are
unchanged. Separate dependency/artifact review is recorded in the legacy audit;
furl/orderedmultidict remain installed, and no OAuth contents/validity are inspected.

Collection selects **901 of 944 tests**, with **43 deselected**. Against disposable
PostgreSQL 16, system/migration checks and **901 offline tests** pass at **91.27%
combined coverage**, retaining the 35% gate; XML export succeeds. The count drops
by the one retired projection-only parameter case, and coverage rises because
legacy source is removed, not because new behavior is covered. All **21 Chromium
cases pass**, with **923 deselected**. Ruff/format, requirements drift, source/
command-discovery preservation, documentation links and whitespace checks pass.
No application records, exported fixture contents or OAuth files are changed;
no live loader, authenticated request, actual Git commit or push is performed.


## Follow-up: remove the retired video command's exclusive URL dependencies

Remove only **furl 2.1.0** and **orderedmultidict 1.0.1** from project metadata,
lockfile and generated requirements. No tracked code consumer remains following
upd_vids retirement; orderedmultidict was required only by furl. Lock comparison
confirms exactly those removals, no additions and unchanged retained versions.
A fresh 65-package sync confirms both are absent while six, python-dateutil and
django-shortcuts remain. Dependency, lock/export and Ruff/format checks pass.

Against disposable PostgreSQL 16, Django system/migration checks, **901 offline
tests** (**43 deselected**) at **91.27% combined coverage**, the unchanged 35% gate
and XML export pass. All **21 Chromium cases pass** (**923 deselected**). Whitespace
checks pass. No app code, schema, fixture exports, OAuth files, task/CI/hook
behavior or stored data change; no live NHL calls. Run `make sync` to prune the two
packages from an existing uv environment.


## Follow-up: retire unused legacy fixture exports

Remove the six `players/fixtures/*_objects.json` exports left by the retired
json_fixtures_creator command. The only remaining filename references were in
an already-disabled session database-loading fixture, now removed with its unused
call_command import. No active consumers, fixture declarations or FIXTURE_DIRS
setting were found. Current synthetic test fixtures remain; no application data,
models/migrations, OAuth files, commands, task/hook/CI behavior or dependency
metadata changes. Historical export contents remain in Git history.

Collection still selects **901 of 944 cases**, with **43 deselected**. Against
disposable PostgreSQL 16, system/migration checks, **901 offline tests** at
**91.27% combined coverage**, the unchanged 35% gate and XML export pass without
the old exports. All **21 Chromium cases pass**, with **923 deselected**. Static,
requirements drift and whitespace checks pass. No application database or live
NHL service is accessed; no fixtures are loaded into application records.

## Follow-up: require POST and CSRF for saved-player mutations

Favorite/comparison toggles and comparison reset now reject GET/HEAD with 405
and use Django's existing CSRF middleware for POST. The base template supplies a
masked token; shared AJAX setup sends it only to the same origin. All mutation
controllers use POST, while table reads and mode switches retain GET. Generated
Players-table favorite links now use the canonical trailing-slash URL so a POST
does not depend on an APPEND_SLASH redirect. Season and mode query parameters,
authentication responses, ownership and sequential quotas retain their contracts.

Eighteen new integration cases cover both player types, safe-method rejection,
missing/invalid tokens, untrusted origins and valid POST persistence, checking
other users and unrelated saved groups throughout. One new Chromium scenario
exercises favorite/comparison add/remove and an intercepted external request
that must not receive the CSRF header. The shared browser harness checks POST
and CSRF headers for every saved mutation, including existing removal/reset and
failure/recovery cases.

Against disposable PostgreSQL 16, Django system/migration checks and **919 offline
tests** pass (**44 deselected**) at **91.28% combined coverage**; the 35% gate and
XML export pass. All **22 Chromium cases pass**, with **941 deselected**. Ruff,
format, JavaScript syntax, workflow YAML, requirements drift and whitespace checks
pass. No application database or live NHL calls are used. No schema or dependency
changes are needed. Concurrent quota enforcement remains separate work.

## Follow-up: serialize concurrent saved-list mutations

All favorite/comparison toggles and comparison resets now take the same user-row
lock inside an atomic transaction before membership checks, quota counts and
writes. One existing account row coordinates empty lists and favorites across
both player tables. Comparison payload rendering stays in the transaction so a
failure rolls back its mutation. Other users can proceed independently. Existing
POST/CSRF, response, selection and sequential quota contracts remain intact.

Twenty-three added transaction cases use real PostgreSQL connections and
authenticated POST requests. The first request is paused after acquiring its
lock; `pg_blocking_pids` must identify it as blocking the second request before
release. Cases cover shared favorites' final slot (including mixed player types),
per-type comparison limits, same-player toggles, removal/addition at capacity,
reset/toggle ordering, independent accounts and rollback after rendering failure.
Limits are not mocked. Worker waits are bounded and connections are closed.

Against disposable PostgreSQL 16, system/migration checks and **942 offline tests**
pass (**44 deselected**) at **91.30% combined coverage**; the unchanged 35% gate
and XML export pass. All **22 Chromium cases pass** (**964 deselected**), as do
Ruff/format, requirements drift and whitespace checks. No schema/dependency
changes, application database access or live NHL requests are involved. Existing
over-quota data is retained; all future application writers must follow the same
locking protocol. Arbitrary direct ORM/admin writes are not a database quota constraint.

## Follow-up: targeted game/date refreshes

Add repeatable, mutually exclusive `upd_gms --date` / `--game-id` selectors and
started/active/final filters. Targets bypass broad season/date traversal, defer
known pregame games before report calls and replay finished games. Boxscore IDs,
dates, team identities and supplied rosters are validated before per-game atomic
publication; required fetch failures retain existing publication. Previously
committed targets survive a later failure. Partial target sets cannot promote
whole-day flags. Saved-date and conflicting same-date log identities are rejected
for explicit review. Existing no-argument broad orchestration is unchanged.

Missing report fields preserve valid matching-game saved values; fresh boxscore
values, including zero, still win. New unavailable fields are JSON null and render
as dashes on game, profile and gamelog pages, rather than fabricated zeros.
Historical broad-loader zeros are not reclassified. Forty-six added integration
cases reuse existing roster/HTML fixtures and exercise actual command parsing,
bounded scope/state selection, replay, day flags, report preservation, date/ID
errors, three rendered pages and rollback after partial player publication.

Against disposable PostgreSQL 16, system/migration checks, **988 offline tests**
(**44 deselected**), **91.44% combined coverage**, the unchanged 35% gate and XML
export pass. All **22 Chromium cases pass** (**1010 deselected**). Static/format,
requirements drift, local documentation links and whitespace checks pass. No
application database or live loader was used for validation. Public historical
NHL schedule/boxscore JSON was inspected read-only to confirm the target metadata
shape; test HTTP is mocked. No schema, dependency, Make/task sequence, scheduler
or deployment settings change. Shared overlap/cooldown guards remain next.

## Follow-up: loader overlap protection and run-status logging

Add migration 0048's `LoaderRun` table and a common management-command execution
guard. One stable, non-waiting PostgreSQL advisory lock covers all four supported
loaders (both totals/game modes) and TOI repair, including direct CLI/Make and
Celery's existing command calls. Read-only audit/status commands remain unlocked.
Conflicts record skipped and raise a command error before network/business-data
work; existing command ordering and transaction boundaries are preserved.

Durable UUID/scope/status/timing/progress/error records and stderr/application-log
events expose running/succeeded/failed/skipped/interrupted outcomes. Phase
progress is throttled to fifteen seconds with phase/end updates. The read-only
`loader_status` command returns recent records or a selected UUID. Lost/replaced
database sessions cannot continue writes; process exit releases the lock, and a
later owner marks abandoned runs interrupted without assuming earlier commits
were rolled back. Rollout requires migrations and updated cooperating writers.

Twenty-one added PostgreSQL cases use independent sessions and a terminated
child process to cover contention, release, crash recovery, progress throttling,
status reads, original failures and eager Celery entry. Existing command tests
now use real committed transactions, because externally wrapped writer commands
are rejected rather than releasing their guard before a caller commits.

Against disposable PostgreSQL 16, system/migration checks, **1009 offline tests**
(**44 deselected**), **91.64% combined coverage**, the unchanged 35% gate and XML
export pass. All **22 Chromium cases pass** (**1031 deselected**). Ruff/format,
requirements drift, documentation-link and whitespace checks pass. Application
data and live NHL endpoints are not accessed by validation; no broker/services
are started. Shared cross-run cooldowns and task retry/expiry remain separate
work; existing per-request Retry-After behavior is retained.

## Follow-up: split Celery work and configure opt-in schedules

Add separate discovery/live/recent-final/daily/weekly/cleanup tasks, persisted
`ScheduledGame`/`LoaderScheduleState` tables in migration 0049, and validated
environment-backed UTC schedules. Automation defaults to disabled. Existing AMQP
dependencies support the selected RabbitMQ transport; no dependency versions
change. The legacy manual task retains its body and is not scheduled. Queue
routing, expiring publications, per-job locks, attempt/completion markers and
quiet-window gating bound duplicate/stale work and preserve maintenance ordering.
Discovery uses schedule dates and aware starts, including Pacific-midnight/DST
boundaries. Final retries stop after a persisted 60-minute observation window;
daily work revisits three previous schedule dates.

Exhausted writer 429s now establish a shared persisted cooldown respecting the
greater of the configured floor and remaining Retry-After. Manual and scheduled
writers cannot bypass it. New scheduled tasks return deferred for busy/cooldown
outcomes without immediate whole-task retries; other failures remain visible.
Terminal loader history defaults to thirty-day retention and task results seven
days. Reviewed service examples and a broker/worker/Beat runbook are included;
no broker, service, application database or live loader is started by this change.

Thirty-three added cases cover disabled/configuration defaults, broker/option
validation, routing/expiry, Celery's default-cleanup entry behavior, persistent
discovery/final windows, state/due selection, maintenance ordering/deferral/failure,
retention, shared cooldowns and cross-session coalescing. Configured clocks/options
are isolated from the local environment. Existing eager task and loader guard
contracts remain covered.

Against disposable PostgreSQL 16, system/migration checks, **1042 offline tests**
(**44 deselected**), **91.68% combined coverage**, the 35% gate and XML export pass.
All **22 Chromium cases pass** (**1064 deselected**); the final focused scheduler/
guard/task selection passes **59 cases**. Ruff/format, requirements drift,
documentation links, service-example syntax and whitespace checks pass. Tests use
mocked HTTP and no broker. Real broker connectivity, host services, controlled
activation and backup/restore rehearsal still need host validation; browser
auto-refresh is separate work.

## Follow-up: browser auto-refresh and freshness

The offline gate passes **1050 tests**, with **48 deselected** (22 external and
26 browser), at **91.80% combined line/branch coverage**. The 35% gate is unchanged.
Eight new isolated PostgreSQL cases protect read-only game/scoreboard endpoints,
strict identity/date selection, viewer-specific favorite controls, private/no-store
responses, saved-versus-checked timestamps, stale unfinished versus old final games,
missing supplementary values and escaped scoreboard results. Repeated checks do
not change saved game/player records or call NHL services.

Four new Chromium scenarios cover automatic saved-data updates, retained sorting
and focus, a pinned scoreboard date/new game, failure/manual recovery, paused and
hidden-tab polling, and a favorite POST racing an older refresh response. The
race changes only the fixture user's intended favorite membership; game/player
columns remain unchanged. Frontend assets, synthetic fixtures and temporary
PostgreSQL keep this independent of live NHL, a broker or the application database.
All **26 Chromium cases** pass (**1072 deselected**). System/schema checks, Ruff
and dependency-export consistency also pass.


## Follow-up: unattended loader/Celery logging

The offline gate passes **1064 tests**, **48 deselected**, at **91.82% combined
coverage**; the 35% gate is unchanged. Thirteen logging cases plus the added
console-startup variant cover routing, UTC JSON, task/run correlation, severity,
tracebacks, context cleanup, nonfailure outcomes, Celery/pool setup and reopening
rotated files. All 72 focused logging/scheduler/loader cases pass. System/schema,
Ruff, dependency-export and adapted service/logrotate syntax checks pass. No live
broker, NHL request, application database or server configuration was used/changed.


## Follow-up: read-only scheduler health

The offline gate passes **1089 tests**, **48 deselected**, at **92.04% combined
coverage**, with the 35% gate unchanged. Twenty-five new cases cover SELECT-only
inspection, missing history, cadence/grace and midnight/weekly deadlines, real
CLI JSON/exit codes, publication versus attempt evidence, cooldowns, scoped failure
recovery, long-running work and display limits. All 79 focused health/scheduler/
loader cases pass. System/schema, Ruff and dependency-export checks pass; no live
services, application database or scheduler state were changed by validation.


## Follow-up: JSON API foundation

The gate passes **1128 offline tests**, **48 deselected**, at **92.04% combined
players coverage**; scope and the 35% gate are unchanged. Thirty-nine API contract
cases cover schema validation/zero-query export, JSON errors, session/CSRF policy,
request correlation and legacy boundaries. `nhl_web_app.api` is explicitly outside
the existing percentage. All **26 Chromium cases** pass on standalone rerun after
one initial-table/static-load timeout in the concurrent run. System/migration,
lint/export and dependency checks pass; no application database or live API was used.


## Follow-up: saved scoreboard JSON endpoint

The offline gate passes **1168 tests**, **48 deselected**, at **92.20% combined
players coverage**, keeping the 35% gate/scope. Forty new cases cover exact dates,
strict inputs, nullable verified legacy scores, side ambiguity, pagination and
whole-date freshness, public privacy, OpenAPI and two-query SELECT-only reads.
Existing refresh/page/API regressions remain covered. System/schema, lint and
export checks pass. Validation uses synthetic PostgreSQL and mocked upstream data.
All **26 Chromium cases** pass (**1190 deselected**) on rerun. The first browser
run had a local-script `net::ERR_NETWORK_CHANGED` failure; no application/test
change was made to obtain the passing repeat.


## Follow-up: saved game-detail JSON endpoint

The gate passes **1219 offline tests**, **48 deselected**, at **92.44% combined
players coverage**, retaining the 35% gate/scope. Fifty-one new cases cover typed
rosters, exact-date/identity verification, null/zero/unit handling, malformed data,
legacy collisions, read-only eight/ten-query bounds, privacy and shared schema/
scoreboard contracts. The focused run passed 146 related cases. System/migration,
schema validation, lint and dependency-export checks pass; synthetic PostgreSQL
and mocked NHL inputs are used, without accessing the application database.
All **26 Chromium cases** also pass (**1241 deselected**); existing refresh,
favorites/comparison and team workflows remain protected.


## Loaded seasons API — 2026-11-10

The dedicated synthetic PostgreSQL offline run passes **1235 tests**, with
48 external/browser tests deselected, at **92.24% combined players line/branch
coverage**. The existing scope and 35% gate are unchanged. Sixteen new cases cover
loaded SBS discovery, shared legacy defaults, missing/malformed rows, pagination,
query validation, public/read-only behavior and OpenAPI. Shared discovery moved
from `player_table` into `players.seasons`; historical coverage figures above are
retained. Django system/migration checks, schema validation, formatting/lint and
dependency export checks pass. Chromium was not rerun for this backend-only slice.


## Players catalogue API — 2026-11-10

The full offline repeat passes **1309 tests**, 48 deselected, with **92.94%
combined players line/branch coverage**. Scope and the 35% gate are unchanged.
Seventy-four new catalogue cases extend existing season fixtures; the focused API
and legacy-table run passes 201 tests. They cover season membership, stale data,
trades, averages/rates, nulls/units, named filters, global ordering/pagination,
public ownership boundaries, bounded read-only queries and typed OpenAPI output.

The initial full run had one existing loader child-process startup timeout
(1308 passed); its separate 21-test file and the full repeat passed without a
loader/test change. Schema/system/migration, formatting/lint and dependency export
checks pass. Chromium was not rerun for this backend-only slice.


## Teams APIs — 2026-11-10

The offline gate passes **1369 tests**, 48 deselected, at **93.13% combined
players line/branch coverage**, with scope and the 35% gate unchanged. Sixty new
cases extend existing team/trade fixtures; the focused API and legacy run passes
284 tests. Coverage includes team identity/listing, season-preserving detail links,
exact skater/goalie splits, defaults, historical/empty data, combined-only and
malformed rows, named filtering/order/pagination, private-state exclusion and
bounded read-only queries with larger populations.

Schema validation, Django system/migration checks, lint/formatting and dependency
export checks pass. Chromium was not rerun for this backend-only slice.


## Player profile/history/gamelog APIs — 2026-11-10

The full offline gate passes **1449 tests**, 48 deselected, with **93.42% combined
players line/branch coverage**. Scope and the 35% gate are unchanged. Eighty new
cases extend season/trade/game fixtures; 439 focused API/legacy tests pass.
Coverage includes typed identity, separate season/career packets, historical team
contributions, zero/missing/invalid data, orphan/ambiguous/undated gamelogs, shared
game-detail verification, named filters/order/pagination, private-state exclusion
and bounded read-only query counts with larger histories.

Schema validation, Django system/migration checks, lint/formatting, dependency
export and documentation-link checks pass. Chromium was not rerun for this
backend-only slice; legacy rendered profile/game tests are included offline.


## Session/CSRF authentication API — 2026-11-10

The full offline gate passes **1504 tests**, 48 deselected, at **93.42% combined
players line/branch coverage**, with scope and the 35% gate unchanged. Fifty-five
new lifecycle/security cases cover anonymous-login CSRF, token/session rotation,
account switching, credential failures, expired/inactive sessions, media/body
validation, username/password compatibility, HTTPS and alternate CSRF storage.
The focused API/legacy run passes 516 tests. Auth code under `nhl_web_app.api`
is tested explicitly but is outside the measured players scope.

An existing game-detail sentinel check now targets statistics fields, avoiding
false positives from timestamps containing `09:59` or `999`. Schema, Django
system/migration, formatting/lint, dependency-export and local documentation-link
checks pass. Chromium was not rerun for this backend-only slice.


## Registration API — 2026-11-10

The full offline gate passes **1553 tests**, 48 deselected, at **93.42% combined
players line/branch coverage**. Scope and the 35% gate are unchanged. Forty-nine
new registration cases bring the focused API/legacy run to 565 tests. They cover
shared form/password policy, normalization, hashing, privilege rejection, session
preservation, CSRF/media errors, profile-failure rollback, real API/HTML case-variant
races and an external exact-username constraint race.

Registration code under `users` and `nhl_web_app.api` remains outside the measured
players scope and is exercised explicitly. Schema, Django system/migration,
formatting/lint, dependency-export and documentation-link checks pass. Chromium
was not rerun; existing rendered auth/registration tests run in the offline gate.
