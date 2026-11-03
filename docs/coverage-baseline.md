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

The GitHub Actions workflow uses Ubuntu 22.04, Python 3.7.17 and an isolated
PostgreSQL 16 service exposed on localhost:5432. It installs the verified
`requirements-bootstrap.txt` tools, installs `requirements.txt`, runs `pip check`,
Ruff and syntax checks for the four season-table JavaScript controllers, and runs
`make test-ci`. pytest-django creates `test_nhl_ci` with real migrations; no loader
commands run and live API tests remain excluded. The workflow uses read-only
repository permissions, no application secrets and no deployment steps.

After tests, CI exports `coverage.xml` and uploads it as `coverage-python37` for
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
