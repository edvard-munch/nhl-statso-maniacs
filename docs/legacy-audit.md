# Legacy command and dependency inventory

Reviewed 2026-11-06 against the tracked checkout and the locked Python 3.12
installation. This is an inventory, not a removal or repair commit. No legacy
command, worker, scheduler, OAuth flow or application-data query was executed.

## Evidence and limits

The review covers tracked command source, AST imports/calls, Make targets,
`players/tasks.py`, Celery/settings configuration, the Procfile, GitHub workflow,
profile views/templates, tests and installed dependency metadata. Django command
**discovery** was inspected without importing/running individual commands.
Dependency reverse edges were evaluated for Python 3.12 with no optional extras.
They identify mandatory relationships, not every dynamic/optional consumer.

No cron, systemd timer/service, supervisor or Celery beat schedule is tracked.
The GitHub workflow runs checks on push/PR/manual dispatch, not NHL update jobs.
That does not establish whether another machine or hosting service schedules them.
Local shell aliases, crontabs, service definitions, broker/beat state and deployment
configuration were not inspected. "No repository caller" is not proof of no use.

## Supported entry points to retain

| Entry point | Repository evidence and behavior |
| --- | --- |
| `upd_tms`, `upd_pls`, `upd_pls_tot`, `upd_gms` | Supported loaders with mocked persistence coverage and opt-in live source contracts. `make update-daily` runs players → current totals → games; `update-all` prepends teams; `update-history` explicitly runs full totals. Keep. |
| `audit_game_toi` | Documented audit/targeted repair workflow and integration contracts. Default is read-only; explicit `--repair` writes verified fields. Keep. |
| `players.tasks.upd_database` | Celery task calls teams → players → games. It **does not call `upd_pls_tot --mode=current`**, unlike the Make sequence. Existing task-order/failure tests preserve that behavior. No tracked scheduler invokes the task; actual worker/beat use needs confirmation. Keep pending a separate orchestration decision. |
| `nhl_web_app.celery_settings.debug_task` | Bound diagnostic task; no repository caller found. Registered with the exported Celery app. No removal in this audit. |
| `scripts/run_hook_tests.py`, `export_requirements.py`, `prepare_browser_assets.py` | Used by Make, hooks, CI or documented browser setup. Keep. |

Sources: [Makefile](../Makefile), [tasks](../players/tasks.py),
[task tests](../players/tests/integration/tests_celery_runtime.py),
[Celery setup](../nhl_web_app/celery_settings.py), [workflow](../.github/workflows/tests.yml).
Celery is imported at package startup and its Django result app/backend is configured;
absence of a visible scheduler is not a reason to remove Celery/results dependencies.

## Retired top-level legacy commands

The four commands below are now removed following explicit user approval. Their
source-review findings are retained here as history; implementations remain in
Git history. The projection-only HTTP retry parameter case/import is also removed.
Stored fields, profile rendering, fixtures and OAuth files are preserved. The five
supported commands remain discoverable; Make and Celery orchestration are unchanged.

| Command | Historical classification and evidence | Disposition |
| --- | --- | --- |
| `upd_pls_proj` (retired) | **Broken API contract.** Concatenates the current `PLAYER_ENDPOINT_URL` template without formatting its `{}` placeholder, appends an ID/hydrate query and expects retired `people/stats/splits` data. Writes `proj_stats`. The former mocked HTTP test covered retry plumbing, not endpoint validity. | Retired. Keep stored projection stats and UI until a separate product decision. |
| `upd_vids` (retired) | **Unavailable in the locked environment / manual workflow.** Imports `googleapiclient` and `oauth2client`, neither installed nor declared in the lock. Uses browser/input OAuth, credential storage and YouTube API calls, then writes `relevant_video`/`video_link_updated_at`. No Make/task/CI caller or command regression coverage found. | Retired. Preserve stored video fields/UI and the 22 OAuth-related JSON files pending a separate artifact review; credential validity is not established. |
| `upd_pls_sbs-n` (retired) | **Legacy season experiment / removal candidate.** Still discovered despite the hyphen. Hardcodes 2018–19, builds the same unformatted landing/hydrate URL pattern and expects nested legacy season rows; writes `sbs_stats`. No repository caller/test found. | Retired. Historical SBS data and supported current/full totals loaders are retained. |
| `json_fixtures_creator` (retired) | **Manual data-export utility / removal candidate.** Reads every team and up to ten records of each other model, overwriting six tracked `players/fixtures/*_objects.json` files. It does not itself mutate DB records. No active test/CI caller or fixture-name consumer found; old `loaddata` examples are commented out. | Retired. Preserve the six exports for separate review; current synthetic `players/tests/fixtures` are distinct and retained. |

The profile still consumes these data fields: [view context](../players/views.py)
conditionally supplies `proj_stats`, and the [profile template](../players/templates/players/player_detail.html)
renders projection rows and `relevant_video`. Retiring a writer does not authorize
removing these fields, historical values, rendering or related migrations.

A local ignored `players/management/commands/endpoints.py` was also found by Django
discovery. It is not tracked and is excluded from the clean-checkout inventory;
`.gitignore` does not prevent Django discovering a file on disk. Its contents and
behavior were not inspected or changed. Check local scratch commands separately
when comparing command lists between machines.

## `_new/` experiments

The user confirmed these six experiments are unused and approved retirement.
They have now been removed; the table below preserves the source-review findings,
with implementation history available in Git. Django's normal command discovery
already excluded `_new`, and no tracked code imports/callers were found.

Read-only URL probes before removal returned 404 for the old NHL stats reports
(after HTTP-to-HTTPS redirects), TLS connection errors for the old statsapi/
bamcontent hosts, and 502 for the sampled HTTP statsapi boxscore. These observations
are point-in-time checks, not proof of permanent host removal. Several scripts
contained DB writes; they were not executed to verify them. No stored data is
removed as part of retiring their source files.

Retirement checks confirm exactly six source deletions, no remaining code callers,
unchanged discovery of the nine tracked top-level commands and valid audit links.
Django system/migration checks, 902 offline tests at 90.86% combined coverage,
the 35% gate and XML export pass against disposable PostgreSQL. Static/format,
requirements drift and whitespace checks pass. No live requests or application
records are involved in retirement validation.

| File | Observed purpose and blockers |
| --- | --- |
| `check_sbs.py` (removed) | Despite its name, rewrites SBS/averages, multi-team bookkeeping and debut fields. Uses retired statsapi year-by-year shapes. Not a read-only audit. |
| `fetch_pics.py` (removed) | Incomplete headshot download experiment. Uses `Goalie.all()`/`Skater.all()` rather than model managers and then treats `values_list` rows as model instances; no completed image-save step. Uses old bamcontent URLs. |
| `upd_pls_NEW.py` (removed) | Older player metadata/stat importer with ORM/image/flag writes and old NHL stats/headshot URLs. No current loader-contract coverage. Compare with supported `upd_pls` before considering any unique behavior. |
| `upd_pls_fw.py` (removed) | Historical faceoff/SBS repair over hardcoded 1996–2018 seasons; rewrites nested rows and bookkeeping via old NHL stats routes. Current `season_loading` covers faceoffs using different row contracts. |
| `upd_pls_logs_fw.py` (removed) | Faceoff gamelog backfill scoped to October 1–10, 2018, using retired statsapi schedule/boxscores and old list-shaped gamelogs. Current gamelogs are keyed by date. |
| `upd_pls_multiseas_goalies.py` (removed) | Historical goalie team-split insertion over 1990–2018, old report routes and nested SBS/count bookkeeping. Compare unique cases with supported team-scoped season loading before retirement. |

## Dependency candidates and consumers

Versions below remain unchanged. A missing direct import alone is insufficient to
remove a package: check runtime/plugin selection, reverse dependencies and behavior.
The generated requirements export is not a second source of truth; changes must
start in `pyproject.toml` and regenerate the lock/export.

| Package or chain | Evidence | Proposed disposition |
| --- | --- | --- |
| `mccabe 0.7.0`, `pycodestyle 2.9.1`, `pyflakes 2.5.0` | No tracked imports/commands or active mandatory reverse edges. Make, hooks and CI use Ruff; no flake8 command/config found. | Removed in the first focused cleanup follow-up. Ruff and its configuration are retained; other package versions are unchanged. |
| `attrs 19.3.0`, `more-itertools 7.2.0`, `py 1.11.0`, `pyparsing 2.4.2` | Legacy compatibility pins with no tracked direct imports or active mandatory reverse edges in the locked Python 3.12 installation. | Removed in the separate test-tool cleanup follow-up. All retained versions, including django-shortcuts, are unchanged. |
| `django-shortcuts 1.6` | Provides the `django` console command, including `r` → `runserver`, `m` → `migrate` and `mm` → `makemigrations`. The user confirmed using these shortcuts. No app import is needed for this CLI consumer. `django.shortcuts` is a separate Django module. | Keep: confirmed developer workflow dependency. Use `uv run --locked django ...` to select the locked interpreter. |
| `furl 2.1.0` → `orderedmultidict 1.0.1` | The only tracked `furl` import was the retired `upd_vids` OAuth URL parser. No code caller remains; `orderedmultidict` is required by furl. | Review/remove the now-exclusive chain in a separate dependency commit; both pins are retained in this retirement batch. `six` has other consumers and is not part of that removal assumption. |
| `gevent 24.11.1` → `greenlet 3.1.1`, `zope.event 5.0`, `zope.interface 7.2` | No direct application imports. The child packages have active gevent reverse edges; Celery can select an optional gevent worker pool externally. No tracked worker launch/pool config found. | Confirm real worker/deployment pool settings before deciding. Eager Celery tests do not prove worker-pool compatibility or disuse. |
| `chardet 3.0.4` | No mandatory reverse edge or direct app import, **but Requests currently selects it as `requests.compat.chardet`**. | Not unused in current behavior. Retain until a deliberate encoding change is tested against JSON/HTML/image/network paths. |
| HTTP/TLS, Pillow, PostgreSQL, Celery/results, Django integrations and pinned build tools | Supported code/config, dependency edges or existing validation require them. | Retain in this audit. Do not remove whole transitive chains based on an import search. |

The missing `google-api-python-client`/`oauth2client` video dependencies are a
command support gap, not packages to remove. A separate deployment gap also exists:
[Procfile](../Procfile) runs `gunicorn nhl_web_app.wsgi`, but gunicorn is absent from
both metadata/lock and the locked installation. Confirm whether that Procfile is
used by the actual host; if it is, add a reviewed server dependency and startup
validation in a focused deployment commit. Do not assume local Django/WSGI import
checks validate that executable or the host's process setup.

## Follow-up decisions and commit boundaries

1. Confirm usage on both development machines and any host: cron/timers, service
   launchers, shell aliases, Celery worker/beat jobs, manual repair scripts and
   whether the Procfile is used. Record command arguments and interpreter, without
   copying credentials into documentation.
2. Completed: remove the unused legacy lint pins in a focused dependency
   follow-up, regenerating lock/export. The old test-helper pins are removed in a
   separate follow-up. Retain django-shortcuts: its CLI use is confirmed.
3. Completed: retire the six `_new` experiments and, in a separate batch, the four
   top-level legacy commands. Review exclusive dependencies, fixture exports and
   OAuth files separately; preserve stored fields/UI unless a separate product/
   data migration is agreed.
4. Decide whether the Celery update task should match the Make sequence. This
   changes behavior and existing task-order tests, so keep it separate from cleanup.
5. Resolve the Procfile/server gap as part of the previously deferred deployment
   rehearsal if that entry point is actually used.

The original inventory changed no command code, dependencies, fields, fixtures,
credentials, schedules or task ordering. PostgreSQL, NHL/YouTube and OAuth were
not contacted. Documentation links and repository evidence are checked; no loader
or application-data test run was needed for the original documentation-only commit.

The first lint cleanup follow-up is validated separately: a clean 71-package uv
environment contains none of the three removed tools; dependency/static/export
checks, 902 offline tests at 90.86% coverage and 21 Chromium cases pass against
disposable PostgreSQL. Run `make sync` to prune these tools from an existing uv
environment; no other dependency versions change.


The separate test compatibility follow-up removes attrs, more-itertools, py and
pyparsing. A clean 67-package sync, both real test hooks in a temporary checkout,
902 offline tests at 90.86% coverage and 21 Chromium tests pass. django-shortcuts
remains installed; stub CLI checks preserve r/m/mm mappings and interpreter
selection without starting the application or running migrations. Other dependency
versions are unchanged; run `make sync` to prune the removed packages locally.


## Separate reviews after top-level command retirement

These artifacts are deliberately retained; command removal does not delete or
regenerate any of them:

- **Dependencies:** `furl` has no remaining tracked code import or mandatory
  dependent; `orderedmultidict` is required by furl. Both stay in metadata/lock/
  export for a separate removal and validation batch. `six` and python-dateutil
  have other consumers and are not exclusive to the video command. The missing
  Google API/OAuth client libraries are not installed and need no uninstallation.
  `django-shortcuts` stays for its confirmed CLI use.
- **Fixture exports:** six tracked JSON files contain 31 teams, 10 goalies,
  10 skaters, 6 games, 6 sides and 157 gamedays. Only record counts/model labels
  were inspected, without exposing record contents. These counts differ from the
  retired exporter's current ten-record limit for non-teams, so regenerating them
  would not preserve the existing artifacts. No active test/CI consumer was found;
  confirm external/manual use before a distinct artifact-removal decision.
- **OAuth artifacts:** 22 tracked JSON files under the former command's
  `credentials/` directory are preserved. No remaining tracked source references
  those filenames/client libraries were found. Contents, token validity and Google
  project/consent ownership were not inspected; no credential was used or revoked.
  Review retention/ownership separately before deleting files or changing access.
- **Related application code/data:** projection/video fields, rendering and the
  OAuth callback route/view remain. Their removal would be a separate behavior/
  schema decision, not part of retiring command entry points.


Command-retirement validation finds exactly five supported top-level commands,
no remaining code caller/import for the four removed commands and unchanged
artifact/model/UI/task/Make/dependency files. Removing the obsolete projection-only
transport parameter case reduces the offline count by one: **901 tests pass**,
with **43 deselected**, at **91.27% combined coverage**. The coverage increase
reflects retired legacy code rather than newly tested behavior. Django/migration
checks, the unchanged 35% gate, XML export and **21 Chromium tests** pass against
disposable PostgreSQL. Static/export/link/whitespace checks pass. No application
loader or authenticated OAuth request is run.
