# Loader overlap protection and run status

The supported loader command entry points share one non-waiting PostgreSQL
session advisory lock: `upd_tms`, `upd_pls`, both `upd_pls_tot` modes, broad and
targeted `upd_gms`, and `audit_game_toi --repair`. It covers the whole command,
including fetches and publication. Make targets, Django shortcuts and Celery's
existing `call_command` sequence use these same guarded entry points.

## Apply the migration and inspect runs

Apply the new tracking-table migration before running loaders:

```bash
uv run --locked python manage.py migrate
uv run --locked python manage.py loader_status
uv run --locked python manage.py loader_status --limit 20 --json
```

`players.0048_loader_run` adds only the `LoaderRun` table and its indexes; the
subsequent `0049_loader_schedule` adds schedule/cooldown state. Apply all pending
migrations, because writer coordination now checks both tables. This does
not modify saved statistics or memberships. `loader_status` is read-only and can
run while a loader holds the lock. `--run-id UUID` selects one record; `--limit`
defaults to ten, with a maximum of 1000. A fresh installation has no run history.

Drain old loader processes before rollout and install this release on every
machine writing to the same database. Older releases and ad-hoc scripts do not
cooperate with this guard. Apply migrations, then restart services with the new
locked environment before enabling further loader invocations.

The table records a UUID, command, whitelisted selector/mode options, status,
start/update/finish timestamps, duration, latest phase progress and failure text.
Terminal states are `succeeded`, `failed`, `skipped` and `interrupted`; an active
run is `running`. Failures retain their original exception/nonzero outcome.
Preflight failures before tracking is available (such as missing migrations or an
unsupported database/transaction context) do not create a run record.

## Contention and recovery

If another cooperating loader is running, the new invocation records `skipped`
and raises `LoaderBusy` (a Django `CommandError`). It makes no NHL requests or
statistics writes and exits nonzero. It neither waits nor retries automatically.
Make stops its remaining stages, and the current Celery task reports failure.
The new scheduled tasks return a deferred payload for this specific outcome,
without immediately retrying it; the old task still fails. A skipped run is visible even though its
business-data work did not start.

The lock is shared across command types, processes and workers using the same
PostgreSQL database. Commands release it on success, failure and handled Python
interruptions. PostgreSQL also releases a session lock when its session ends;
see the [PostgreSQL advisory-lock contract](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS).
There is no lock file to remove or time-based lease that can expire beneath a
slow loader. An alive process stuck in I/O retains the lock; use the run history,
existing request timeouts and service supervision to investigate it.

A hard process exit can leave a `running` record. The next invocation that
successfully acquires the shared lock marks abandoned running records
`interrupted` before creating its own run. This is inferred recovery, not proof
that no data was saved: earlier per-player/per-game/day commits may survive.
The recovered duration includes time until detection and is not an exact crash
time. A read-only status query never marks an old row interrupted just because
its progress timestamp is old.

Commands fail closed if their database connection is replaced/lost and a later
statement would run without the original lock. Require a direct PostgreSQL
connection or a session-affine pool; transaction/statement-pooling proxies are
not supported by this session-lock design. PostgreSQL is required; there is no
SQLite/file-lock fallback.

## Logging and progress

Application log records are JSON lines with UTC timestamps, severity and logger.
`NHL_LOG_DESTINATION=file` (default) writes `logs/nhl_web_app.log` through
`WatchedFileHandler`; `console` writes to stderr for journald and opens no
application log file. See [retention and server setup](celery-operations.md#logging-and-retention).
The `players` logger hierarchy collects HTTP retries and game-loader warnings,
including loggers created before Django setup. Existing third-party loggers stay
enabled. Celery uses the same configuration rather than replacing its handlers.

Loader events include run ID, command/scope, status, elapsed duration and progress.
Failures are ERROR with tracebacks in application logging; interruptions are
WARNING; expected busy/cooldown skips remain INFO with status/reason fields.
Standalone commands also emit their existing plain JSON run events to explicit
stderr; console mode filters out duplicate handler copies. `--verbosity 0`
suppresses those direct run events while database history and file logging remain
available. Other warnings/errors are still logged. Stdout remains available for
existing command output, especially `audit_game_toi --json`; legacy progress and
print output are not converted into structured records.

In Celery, loader events use the configured handler only. Task lifecycle,
scheduler, loader and HTTP messages include task ID/name and the scheduling job
where available; messages inside a loader also include its run ID and scope.
Task start/finish records contain elapsed duration and the actual outcome
(including disabled/not-due/deferred), with failure tracebacks and original
exceptions preserved. Context is cleared between runs/tasks. The lifecycle
wrapper does not serialize task arguments or full results.

Phases cover team updates, player report fetch/publication/flags, current/full
totals, game dates/targets and TOI repair. Progress includes the current item,
processed count, known total/remaining count and target deferrals. Phase changes,
initial/completed phases and the final outcome are logged; intermediate updates
are throttled to fifteen seconds. There is no background heartbeat during a
single long request. Totals can be unknown for broad discovery. Processed means
work completed in that phase, not a guarantee that its enclosing publication
transaction later committed. A failed run's status/error must be read with its
progress and the loader's existing rollback contracts.

Selectors/modes are logged; unrelated command options such as output streams or
settings are excluded. Failure messages are bounded to 2000 characters. A
successful run means the command returned normally, not that the NHL source had
new data or every optional report was available. Inspect targeted deferrals,
warnings and audit reports for missing enrichment. No API freshness timestamp or
source freshness is inferred. A recorded `next_retry_at` is the local cooldown's
earliest eligible retry, not a promise that a later NHL request will succeed.

## Boundaries and remaining scheduling work

This guard preserves existing transaction boundaries; it does not wrap a whole
multi-command refresh in one transaction or roll back previously successful
stages. It is released between Make/Celery stages, so different batches can
interleave sequentially. It protects loader writes, not arbitrary ORM/admin
writes or the separate favorites/comparison quota mechanism.

Programmatic writers must use `call_command`/`LoaderCommand.execute` outside an
enclosing transaction. Otherwise releasing the session lock could precede the
caller's eventual commit; such calls are rejected. Internal `handle` functions
and parsing/publication helpers remain available for isolated unit tests but are
not supported external scheduling entry points and do not acquire the guard.
Tests invoking commands now use real committed transactions to exercise this
boundary, with mocked HTTP and a dedicated synthetic PostgreSQL database.
Read-only `audit_game_toi` and `loader_status` do not acquire the writer lock or
create loader runs.

When opt-in schedules are enabled, terminal run history is pruned after thirty
days; configure application-log rotation on the host. Shared cross-run cooldowns,
task expiry/coalescing and quiet-window deferral are implemented in the
[Celery setup](celery-operations.md). Per-request [Retry-After handling](loader-http.md)
is retained. No periodic work starts without explicit activation; browser polling reads saved data independently.

## Regression checks

`tests_loader_runs_db.py` uses independent PostgreSQL sessions to check
cross-command contention, status reads during a run, progress throttling,
failure/interrupt cleanup, session-change rejection, nested/caller-transaction
rejection and eager Celery integration. A separate child process is terminated
after committing synthetic data to prove crash release and next-run recovery.
Existing command persistence and targeted-refresh regressions still run through
the guarded entry points. Validation never uses the application database.
