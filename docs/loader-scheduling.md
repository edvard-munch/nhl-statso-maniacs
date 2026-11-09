# Loader scheduling policy and server requirements

Status: planning baseline, updated 2026-11-09. The owner confirmed that Celery is not
running and updates should eventually run on an always-on server. This document
does not enable jobs. Explicit [targeted refreshes](game-loading.md#targeted-game-and-date-refreshes)
are now implemented; no-argument `upd_gms` retains its broad behavior. Live freshness, final-refresh
windows, broker choice and host details still need confirmation before activation.

## Current implementation

- `nhl_web_app/celery_settings.py` discovers tasks and loads Django settings with
  the `CELERY_` namespace. Settings configure `django-db` results, but no explicit
  broker URL, Beat schedule or task routing. Loader command execution now uses
  [shared overlap protection and run history](loader-runs.md).
- `players.tasks.upd_database` runs `upd_tms` → `upd_pls` → `upd_gms`. It does not
  run `upd_pls_tot --mode=current` and does not match `make update-all`.
- `make update-daily` runs players → current totals → games sequentially;
  `make update-all` prepends teams. Both stop on failure. Earlier successful
  commands remain committed. These are manual entry points, not schedulers.
- `upd_gms` revisits date ranges and can scan the regular season. For each
  started game it fetches boxscore, right-rail, play-by-play and available HTML
  reports. Fetches and writes currently share a transaction for the whole day.
  One required failure can therefore roll back other games in that day.
- Explicit `--date` or `--game-id` selectors bypass the broad scan, accept
  `--state started|active|final`, defer known pregame games and allow finished
  replays. They fetch before per-game transactions and preserve valid same-game
  report values when fresh reports omit them; new unknown report values are null.
  There is no automatic recent-window discovery or periodic execution yet.
- Only regular-season games are loaded. Playoffs/preseason support is not part
  of this scheduling change. `FINAL`/`OFF` plus a matching stored roster marks a
  game finished; `OVER` and active states remain unfinished. Final status alone
  does not prove all supplementary statistics are available or permanently final.
- Current totals visits all stored players and performs career enrichment;
  avoiding landing calls does not make it a cheap live-refresh job. A reported
  manual run took about 18 minutes, including retries; measure server runtime.
- Updating the database does not refresh an already-open browser page.

## Data freshness policy

Game pages and game logs use game-loader data. Players, team, favorites and
comparison season tables use season rows (`sbs_stats`); career modes use career
aggregates. Refreshing games alone does not refresh season/career tables. See
[season workflow](saved-player-season-tables.md) and [game publication](game-loading.md).

The following intervals are proposed starting values, not enabled schedules or
guarantees about upstream publication. Keep them configurable and measure request
volume, runtime and observed freshness before increasing frequency.

| Job | Proposed cadence | Scope and publication rules |
| --- | --- | --- |
| Schedule discovery | Every 30 minutes when quiet; every 5 minutes within 60 minutes of a scheduled start or while games remain active | Refresh start times/states; discover reschedules. Do not fetch every future boxscore. |
| Live games | Every 2–5 minutes while active; exact target pending owner confirmation | Target active game IDs, not the whole season or the full daily chain. Update supported live fields; preserve previously verified enrichment when reports are missing. |
| Recently finished games | Every 5–10 minutes for an initial 60-minute window after first observing final status | Reconcile rosters and supplementary reports even if the game is already marked finished. Bound retries; unresolved games move to the daily retry/report rather than polling forever. |
| `upd_pls` | Daily in a quiet window | Refresh player identity/roster metadata and season rows. An optional 30–60-minute game-window refresh is a separate choice if season-table freshness is required. |
| `upd_pls_tot --mode=current` | Daily in a quiet window, after successful player refresh | Update season rows and career enrichment. Keep the full all-player job out of frequent live polling. |
| Recent-game reconciliation | Daily in a quiet window | Revisit the previous three NHL schedule dates, including finished games, for delayed reports/corrections. Older repairs remain explicit. |
| `upd_tms` | Weekly before the routine refresh; also bootstrap/season rollover when needed | Refresh team metadata. Missing required teams should trigger a visible dependency failure, not repeated full team loads per live tick. |
| `upd_pls_tot --mode=full` | Explicit manual refresh/backfill | Never include in the live tick or default daily automation. Coordinate with other writers. |

Daily/weekly wall-clock times remain unset until the host and expected runtimes
are known. Defer heavy work when games are active or imminent; expose the deferral
instead of silently missing a day. A long task cannot be preempted merely by
assigning a newer live task higher queue priority.

Live special-team TOI and other report-derived values may be unavailable before
final reconciliation. Preserve known values and represent unknown values explicitly;
do not treat an unavailable report as evidence of zero. Existing strict season
report checks must also remain: reports fetched at different publication times
may disagree, so a rejected refresh retains the last valid batch. Frequent polling
cannot guarantee that season tables include in-progress games. Deriving live
season totals from game events would require a separate design to avoid double counting.

## Clock and game-window rules

Use timezone-aware UTC start timestamps to decide when games are due; do not
hardcode a Moscow overnight window. Early games, changed starts and North American
daylight-saving transitions must work. Moscow times are display conversions
(`Europe/Moscow`), not the source for deciding whether an NHL game is active.

Configure Celery's scheduling timezone explicitly as UTC in the later setup
commit. Django currently ends with `TIME_ZONE = "Europe/Moscow"`; `upd_gms` uses
`US/Pacific` to choose its current date. Preserve API schedule dates and game IDs
when targeting games and recent-day replays; a UTC date is not interchangeable
with an NHL schedule date. Keep polling active/unfinished games across midnight.
Re-evaluate state after reschedules; postpone/cancel handling must be bounded
rather than leaving a game permanently in a frequent-poll loop.

Celery documents timezone handling, the single-scheduler requirement and possible
periodic-task overlap in its [5.4 scheduling guide](https://docs.celeryq.dev/en/v5.4.0/userguide/periodic-tasks.html).

## Server setup requirements

The target is an always-on host. Select the operating system, service manager,
paths and broker before writing an executable deployment runbook.

| Component | Requirement |
| --- | --- |
| Application environment | Pinned Python from `.python-version`, locked uv dependencies and explicit working directory/interpreter for every service. Shell aliases and an activated development venv are not service configuration. See [uv deployment preparation](uv-migration.md#dependency-groups). |
| PostgreSQL | Reachable application database, deployed migrations, backup/restore procedure and appropriate application role. Tests must continue using a separate synthetic test database. |
| Message broker | Choose RabbitMQ or Redis and configure authenticated private connectivity, persistence/recovery and the corresponding Python transport dependencies. Neither service is provisioned by this repository. `django-db` stores task results; it is not the message broker. Redis transport is not currently declared in the lockfile. |
| Worker | Supervised non-root service with restart-on-failure, explicit environment and writable runtime/log/media paths. Start conservatively with a dedicated loader worker and concurrency one; this is not a replacement for cross-process overlap protection. Worker pool choice remains explicit; do not assume the retained gevent dependency means gevent is used. |
| Scheduler | Exactly one supervised Beat instance for this schedule, with persistent writable scheduler state. Worker discovery alone does not create schedules. Code-based Beat entries are the initial proposal; `django-celery-beat` is not currently installed or required by this plan. |
| Secrets/settings | Supply existing Django/PostgreSQL settings to services, and add explicit broker/timezone/routing settings in the implementation commit. Merely exporting `CELERY_BROKER_URL` does not wire it into the current Django settings module. Keep broker credentials out of tracked docs and logs. |
| Network and storage | Outbound HTTPS/DNS for the supported NHL/report/image sources, persistent uploaded media, logs and adequate disk space. Share the same application release/data paths between web and worker services. |
| Web process | Separate from worker/Beat. The existing Procfile names Gunicorn, which is absent from locked dependencies; resolve the actual web-server entry point before deployment. |
| Operations | Service health, queue age, last successful refresh by job/game, failures and rate-limit cooldowns must be visible. Define task-result/log retention so frequent jobs do not grow storage indefinitely. |

See Celery's [broker choices](https://docs.celeryq.dev/en/v5.4.0/getting-started/backends-and-brokers/index.html)
and [supervised service guidance](https://docs.celeryq.dev/en/v5.4.0/userguide/daemonizing.html).
Broker configuration and unit/container files belong to later implementation;
there are no ready-to-enable service definitions in this documentation commit.

## Coordination, failures and progress

Use one shared loader coordination policy for Celery, Make and direct management
commands. It must prevent overlapping/conflicting read-modify-write updates to
player JSON from live, season, career and historical jobs. The saved-list user
locks protect favorites/comparison only; they do not protect loaders.

Initially serialize conflicting loader writes and defer heavy jobs outside the
live window. Coalesce duplicate ticks; do not enqueue an unbounded backlog.
Expire stale live jobs and discover the current due set after downtime instead
of replaying every missed tick. Any finer-grained locking needs tests for shared
players and stale live responses arriving after final reconciliation.

Retain the [bounded HTTP retry and Retry-After policy](loader-http.md). An exhausted
429 must cause a visible cooldown/deferred run, not immediate retries from several
workers. Define a shared cooldown across loader jobs and capped task retries in
the implementation. Missing future boxscores must be deferred explicitly;
malformed required started-game data must still fail without partial publication.
Failures in historical/backfill work must not prevent unrelated due live work.

Every run should log job/run identity, UTC start/end, selected game/date scope,
processed/remaining counts, duration, successes, deferred/failed items and the
next eligible retry. Distinguish successful fetch/publication time from source
freshness: a successful request does not establish that NHL data changed. Expose
incomplete final enrichment and exhausted retry windows for later reconciliation.

## Focused implementation queue and rollout

1. **This commit:** record policy, current limitations and server requirements.
2. **Implemented: targeted game refresh:** explicit game/date selection, bounded
   known-pregame deferral, finished-game replay and preservation of valid
   same-game report fields. Date/state boundaries, missing reports, null rendering,
   replay and per-game rollback have mocked-HTTP/PostgreSQL regressions. The broad
   manual command remains compatible. Selecting recent dates is still explicit;
   the later scheduler will decide when and which games to refresh.
3. **Implemented: overlap protection and run status:** one non-waiting PostgreSQL
   lock covers supported command writers, including TOI repair, through manual
   and Celery entry points. Migration 0048 adds durable run/progress history;
   stderr/file JSON events and `loader_status` expose outcomes. Contention,
   session loss and hard-process-exit recovery have isolated PostgreSQL tests.
   Shared cross-run rate-limit cooldowns, queue expiry/coalescing and scheduler
   retry policy remain the next focused scheduling work.
4. **Celery task split and server configuration:** separate discovery/live/final/
   daily/weekly tasks, explicit broker/timezone, Beat schedule, supervision and
   retention. Protect dependency ordering: weekly teams when due, then players,
   current totals and recent-game reconciliation. An unrelated failed batch must
   not suppress live polling. Preserve/document the old task's compatibility.
5. **Browser freshness:** refresh open game/scoreboard views and show last update,
   stale/partial data and retry behavior without losing user interactions.

Before enabling Beat, confirm host/broker, the desired live interval, whether
season tables need intra-game refresh and the quiet-window/cooldown values.
Validate restart, duplicate delivery, midnight/DST, long-running jobs and rate
limits. Rehearse services with disposable infrastructure and synthetic data,
then verify one controlled server refresh and its logs before enabling periodic
execution. Local eager task tests alone do not validate a broker/worker/Beat setup.
