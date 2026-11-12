# Celery tasks, schedules and server operation

The split tasks and UTC Beat schedule are implemented but **opt-in**. Installing
this release does not enable NHL automation or start a broker/worker/scheduler.
The existing `players.tasks.upd_database` name/body remains available for manual
compatibility (teams → players → broad games, without current totals). It is not
in the new Beat schedule; its routing is now `nhl-maintenance`.

## Tasks and defaults

| Task | Beat cadence | Actual work |
| --- | --- | --- |
| `players.tasks.discover_games` | Every 5 minutes | Refresh the schedule when due: 30 minutes when quiet, 5 minutes near a start or while games are active. One request covers the week starting yesterday in US/Pacific; no future boxscores are fetched. |
| `players.tasks.refresh_live_games` | Every 5 minutes | Use discovered LIVE/CRIT/OVER game IDs, including soft finals awaiting terminal state. Call targeted `upd_gms` with started-state filtering. |
| `players.tasks.refresh_final_games` | Every 10 minutes | Replay FINAL/OFF games for 60 minutes after first observing final status. The window is persisted and is not extended by discovery/restarts. |
| `players.tasks.refresh_daily` | Check every 15 minutes | Once per UTC maintenance date, during the quiet window: teams if weekly/bootstrap is due → players → current totals → final games from the previous three Pacific schedule dates. |
| `players.tasks.refresh_teams` | Check every 15 minutes | Weekly/bootstrap team work, sharing the maintenance job lock with the daily task. Daily work also enforces this dependency; Beat entry ordering is not relied upon. |
| `players.tasks.cleanup_history` | Daily 04:00 UTC | Delete terminal loader-run records finished more than 30 days ago. Retain running records. |
| `celery.backend_cleanup` | Daily 04:15 UTC | Clean task results using the configured seven-day result expiry. |

Default quiet hours are **09:00–12:00 UTC (12:00–15:00 Moscow)**. This is an initial
configurable window, not a measured guarantee that the server is idle. Maintenance
also defers if a known game is active/soft-final or starts within 60 minutes. It
checks the window between stages and marks the daily date complete only after
all stages return normally. A failed batch can repeat earlier idempotent stages
on the next eligible tick; successful earlier writes are not rolled back.

Weekly work defaults to Monday (`NHL_WEEKLY_WEEKDAY=0`); the first eligible
maintenance run bootstraps teams even on another weekday. A missed weekly run
can catch up later in the week. Quiet windows crossing midnight belong to their
UTC start date. No intra-game season-table job or full historical refresh is
scheduled. Live game/log freshness remains separate from season/career tables.

Discovery stores regular-season IDs, API schedule dates, aware UTC starts,
states, discovery time and final-window/attempt timestamps in `ScheduledGame`.
The singleton `LoaderScheduleState` stores discovery/daily/weekly completion and
shared cooldown state. Migration `0049_loader_schedule` adds these tables; it does
not rewrite game statistics. Malformed discovery snapshots are rejected before
publication. Reopened games reset their final window. Non-OK schedule states are
excluded, and active games more than 24 hours past their start are not polled
forever. Old/missing entries and report problems require review/reconciliation;
this is not automatic repair of rescheduled date-keyed player history.

## Broker and environment

This implementation uses **RabbitMQ** through the existing AMQP dependencies.
Provision it separately with a private authenticated application user/vhost.
Redis is not selected and its Python transport dependency is not installed.
`django-db` remains the result backend; it does not replace the broker.

Keep the same reviewed environment on web/worker/Beat services, including existing
Django/PostgreSQL settings. The development `.env.example` lists the new options:

```dotenv
NHL_SCHEDULING_ENABLED=True
CELERY_BROKER_URL=amqp://nhl:REPLACE_PASSWORD@127.0.0.1:5672/nhl
NHL_LIVE_SECONDS=300
NHL_DISCOVERY_SECONDS=300
NHL_QUIET_DISCOVERY_SECONDS=1800
NHL_FINAL_SECONDS=600
NHL_FINAL_WINDOW_SECONDS=3600
NHL_MAINTENANCE_SECONDS=900
NHL_PRE_GAME_SECONDS=3600
NHL_COOLDOWN_SECONDS=300
NHL_QUIET_START_HOUR=9
NHL_QUIET_HOURS=3
NHL_WEEKLY_WEEKDAY=0
NHL_RECENT_DAYS=3
NHL_RUN_RETENTION_DAYS=30
```

Replace/URL-encode real credentials in the private server environment, not this
file. `amqps://` can be used for a TLS-configured broker. Enabling scheduling with
an empty/non-AMQP broker URL fails configuration validation. Interval/window
seconds must be 60–86400; hours/weekdays/date-count/retention bounds are validated
as well. Keep automation false until the host, cadences, credentials, migrations
and service setup have been reviewed. Both Beat and workers must receive the
flag; disabled scheduled tasks return `status: disabled` without work. The old
manual task and management commands remain callable when automation is off.

UTC scheduling is explicit and independent of Django's Moscow display timezone.
Game windows use UTC timestamps; daily recent dates use Pacific calendar dates.
Start times and North American daylight-saving changes are not approximated by
hardcoded Moscow game hours.

## Queues, overlap and rate limits

Discovery/live/final tasks route to `nhl-live`; maintenance/cleanup/legacy tasks
route to `nhl-maintenance`. Initially use one prefork worker with concurrency one
consuming both queues, with prefetch one. A queue name does not preempt a running
heavy job; measure runtimes and keep maintenance away from game windows. Separate
workers are possible later, but all writer commands still share the PostgreSQL
lock and can defer each other.

Beat publications expire after one tick interval, preventing obsolete live work
from running after a long queue delay. Tasks select the current due set at
execution, rather than replaying every missed tick. PostgreSQL job locks coalesce
concurrent copies; last-attempt timestamps limit repeat game work, and daily/weekly
completion dates avoid duplicate successful batches. This is not exactly-once
delivery. Expired messages may remain in a broker until delivery/expiry handling;
monitor queue age/size as well as task results.

The existing writer lock covers discovery requests/publication and all management
commands. Busy/cooldown outcomes return a structured `status: deferred` from new
scheduled tasks, with no immediate Celery retry. Those task results can have
Celery SUCCESS state while their payload says deferred; inspect the payload and
[loader run records](loader-runs.md). Other failures stay failures. A failed game
does not suppress remaining selected games, except a busy lock, shared cooldown
or lost session stops the task. Errors remain visible in per-game loader records.

Exhausted NHL 429 errors now persist a database-wide cooldown for the greater of
`NHL_COOLDOWN_SECONDS` and a valid remaining `Retry-After` delay. Other supported
writer commands, including manual commands, record skipped and refuse NHL work
until it expires. The failed/skipped run's progress includes `next_retry_at`.
Existing bounded per-request retries remain; 404/ordinary errors do not establish
a shared cooldown. Never immediately auto-retry an exhausted whole command.
Read-only audit HTTP calls are not covered by the writer cooldown and should not
be run as additional automated traffic during one.

Schedule metadata/selector queries and housekeeping are not statistics writes.
They use job locks where needed; the global writer lock continues to protect
NHL fetch/publication commands. Require direct/session-affine PostgreSQL, not
transaction-pooling proxies. Run tasks outside a wrapping application transaction.

## Install and operate services

Review the example units in [worker](../deploy/nhl-celery-worker.service.example)
and [Beat](../deploy/nhl-celery-beat.service.example). They assume a non-root `nhl`
account, `/srv/nhl_web_app`, a private `/etc/nhl-web-app.env` and systemd. Adapt
these to the actual host; no units are installed or enabled by this change.
Drain old unguarded loader processes on all writing machines before rollout.

From the deployed checkout, prepare the locked runtime and schema first:

```bash
uv sync --locked --no-default-groups
uv run --locked --no-default-groups python manage.py migrate
uv run --locked --no-default-groups python manage.py check
```

Ensure the service user can read the environment and write application logs/media.
On a fresh database, populate teams, players and current totals through the
supported manual commands before enabling live tasks; verify required identities
and one controlled targeted game refresh. On an existing database, verify those
prerequisites instead of reloading history. The first scheduled quiet-window team
bootstrap is not a substitute for this initial setup during active games.
Provision RabbitMQ separately; verify its connectivity without printing broker
credentials. For an initial foreground check in the same reviewed environment:

```bash
uv run --locked --no-default-groups celery -A nhl_web_app worker --loglevel=INFO --pool=prefork --concurrency=1 --prefetch-multiplier=1 --queues=nhl-live,nhl-maintenance
# A separate terminal, on only one scheduler host:
uv run --locked --no-default-groups celery -A nhl_web_app beat --loglevel=INFO --schedule=/var/lib/nhl-celery/beat-schedule
```

Create the Beat state directory with service-user ownership first; the example
unit's `StateDirectory` handles it when using systemd. Do not combine a foreground
Beat with the supervised Beat. There must be exactly one scheduler for these
entries. After reviewing/copying units, use the host's normal systemd install,
reload and enable procedure. Worker shutdown allows up to 30 minutes to drain;
forced termination may leave partial earlier commits and a recoverable run record.

Inspect worker/service logs, task result payloads, `players.scheduler` events and:

```bash
uv run --locked --no-default-groups python manage.py loader_status --limit 20 --json
```

A normal return proves execution, not NHL source freshness or complete optional
reports. Recently finalized games are attempted within a bounded window even
when reports remain unavailable; the daily reconciliation revisits them later.
Loader history defaults to 30 days; task results seven days. Configure [logging and retention](#logging-and-retention) on the host. Schedule-entry history is retained, not automatically
purged. Broker provisioning, live service startup/health and a representative
backup/restore rehearsal must be verified on the real host; offline tests do not
claim those checks were performed.

Celery's [5.4 periodic-task guide](https://docs.celeryq.dev/en/v5.4.0/userguide/periodic-tasks.html)
explains singleton Beat and overlap, [routing](https://docs.celeryq.dev/en/v5.4.0/userguide/routing.html)
explains queue selection, and [configuration](https://docs.celeryq.dev/en/v5.4.0/userguide/configuration.html)
describes expiry, results and broker settings. Tests use mocked NHL requests and
isolated PostgreSQL, without a running broker or real server services.

## Browser refresh and freshness

The [Vue scoreboard/game pilot](vue-refresh.md) implements the same saved-read
policy below, with explicit offline pausing and request deadlines. Its Last checked
value comes from accepted API metadata; the existing Django pages remain operational.

The scoreboard and game detail page check saved application data every 60 seconds
while visible. They do not call the NHL or start loaders. The scoreboard stays on
its selected day; game tables retain their sort order and favorite controls.
Use **Refresh now** for a manual check or uncheck **Auto-refresh** to pause.
Hidden tabs stop polling and check again when visible. Failed checks keep the
last displayed data and retry with increasing delays, capped at five minutes;
a manual retry is always available.

**Data saved** is the database game's successful publication time, not the NHL's
source timestamp. **Last checked** records a successful browser check and does
not imply the source changed. Unfinished games saved over 15 minutes ago carry
an out-of-date warning; old final games do not receive that warning merely due
to age. Missing saved player or supplementary fields receive an unavailable
warning rather than an invented zero. Scoreboard summary freshness uses the
oldest unfinished game, or the latest save when all games are final; each game
also displays its own save time. With no saved games, the page says so and keeps
checking the selected day. Automatic updates require the worker, Beat and loaders
described above to be running separately.

Refresh endpoints are read-only GET requests with private, no-store responses.
Favorite actions continue to use POST and CSRF; an in-flight refresh started
before a favorite mutation is discarded to avoid restoring an old selection.


## Logging and retention

All application logging uses JSON lines with UTC timestamps and severity. Task
start/finish events carry task ID/name, job, duration and outcome; loader/HTTP
messages carry the associated run ID/command/scope while executing. Find a failing
run with `loader_status`, then search logs by its UUID or the Celery task ID.
Failures are ERROR and include tracebacks; interrupted work is WARNING. Expected
busy/cooldown/window deferrals and not-due outcomes remain INFO with explicit
status/reason fields. A task failure and its loader failure are separate related
events, not two executions. No logging-only retry or behavior change is introduced.

The worker/Beat service examples set `NHL_LOG_DESTINATION=console`, with stdout
and stderr captured by journald. The shared EnvironmentFile can override that
setting, so remove an old `NHL_LOG_DESTINATION=file` or explicitly set `console`
in the server environment. No application file/directory is opened in console
mode. Inspect service logs with:

```bash
journalctl -u nhl-celery-worker.service -u nhl-celery-beat.service --since '1 hour ago' -o cat
```

Legacy loader prints, tqdm output and service startup messages may still be plain
text; JSON logging does not turn the entire process output into JSON. Existing
log prefixes are replaced by JSON for newly written application records. Celery's
`setup_logging` hook retains Django's handler configuration for worker and Beat;
its `--logfile`/format options do not replace this configuration. INFO is the
configured application/handler threshold. Console log events from a task are
emitted once; standalone command run events still honor their explicit stderr
stream and verbosity. Missing task IDs on manual commands or run IDs on broker/
Beat events are expected.

For bounded server storage, review the optional
[dedicated journal namespace example](../deploy/nhl-journald.conf.example).
If the host supports systemd journal namespaces, add `LogNamespace=nhl` to both
reviewed service units and install the shown namespace retention configuration.
It sets 256 MB persistent / 64 MB runtime budgets and 14-day retention for that
namespace, without changing other host journals. Namespace logs are then read
with `journalctl --namespace=nhl ...` using the same unit filters. Validate namespace
support, persistent storage and retention on the host before restarting services;
otherwise use the host's established journal retention policy. These examples do
not install or change services or journal configuration automatically.

For file logging (the unchanged local default), install and adapt the
[logrotate example](../deploy/nhl-logrotate.conf.example), check directory/account
permissions and verify the host's logrotate timer. It rotates daily or above
20 MB when logrotate runs, retains 14 files and uses delayed compression.
`WatchedFileHandler` reopens after rename/create rotation; do not use copytruncate
or separate in-process rotating handlers in prefork workers. A file can grow
between logrotate invocations, so this is not a strict instantaneous size cap.
Rotate the previous text-format log on rollout if downstream tools require each
file to contain JSON exclusively.

Check one manual run, one worker task and Beat output after deployment: verify
UTC fields, task/run correlation, a controlled failure and log retention without
printing the environment or broker credentials. Automated tests exercise logging
setup, eager task failures and file reopening, without provisioning a broker or
claiming host journal retention has been applied. Log collection does not alert
operators on overdue jobs; monitoring/notifications remain separate work.

The implementation uses Celery's
[logging setup signal](https://docs.celeryq.dev/en/v5.4.0/userguide/signals.html#setup-logging)
and Python's
[WatchedFileHandler](https://docs.python.org/3.12/library/logging.handlers.html#watchedfilehandler).

Journal namespace paths and retention controls follow the systemd
[journald configuration reference](https://www.freedesktop.org/software/systemd/man/255/journald.conf.html).


For a read-only view of saved scheduling evidence, run `scheduler_health` or
`scheduler_health --json`. See [health checks and monitoring exit codes](scheduler-health.md).
This does not activate services or probe the broker/worker/Beat.
