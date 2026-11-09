"""One PostgreSQL session lock for loader writes, with durable run outcomes."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta, timezone as datetime_timezone
import json
import logging
import sys
from time import monotonic

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection, DatabaseError
from django.utils import timezone

from nhl_web_app.logging_config import bind_context, context_fields

from .models import LoaderRun, LoaderScheduleState

logger = logging.getLogger(__name__)
# Stable, application-specific two-int PostgreSQL advisory lock key ("NHLS", 1).
LOCK_NAMESPACE = 0x4E484C53
LOCK_RESOURCE = 1
PROGRESS_INTERVAL_SECONDS = 15
ERROR_LIMIT = 2000
SCHEDULE_STATE_KEY = "nhl"
SCOPE_OPTIONS = (
    "dates",
    "game_ids",
    "state",
    "mode",
    "repair",
    "game_id",
    "season",
    "start_date",
    "end_date",
)
_current = ContextVar("loader_run", default=None)


class LoaderBusy(CommandError):
    """A caller can reschedule later; waiting here would accumulate stale ticks."""


class LoaderCooldown(CommandError):
    """The shared NHL cooldown has not elapsed."""


class LoaderSessionLost(CommandError):
    """Do not retry additional games in a task after losing its database session."""


def record_skipped(command, scope, stream, verbosity, reason, progress=None):
    now = timezone.now()
    run = LoaderRun.objects.create(
        command=command,
        scope=scope,
        status=LoaderRun.Status.SKIPPED,
        updated_at=now,
        finished_at=now,
        duration_seconds=0,
        error=reason,
        progress=progress or {},
    )
    RunReporter(run, stream, verbosity).emit("skipped")


def note_rate_limit(error):
    from . import nhl_http

    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        response = getattr(error, "response", None)
        if response is not None and response.status_code == nhl_http.RATE_LIMIT_STATUS:
            delay = max(
                settings.NHL_SCHEDULING["cooldown_seconds"],
                nhl_http.retry_after_seconds(response.headers.get("Retry-After")) or 0,
            )
            until = timezone.now() + timedelta(seconds=delay)
            LoaderScheduleState.objects.update_or_create(
                key=SCHEDULE_STATE_KEY, defaults={"cooldown_until": until}
            )
            return until
        error = error.__cause__ or error.__context__
    return None


class RunReporter:
    def __init__(self, run, stream, verbosity):
        self.run = run
        self.stream = stream
        self.verbosity = verbosity
        self.started = monotonic()
        self.last_progress = self.started

    def emit(self, event):
        payload = {
            **context_fields(),
            "event": event,
            "run_id": str(self.run.pk),
            "command": self.run.command,
            "scope": self.run.scope,
            "status": self.run.status,
            "timestamp": timezone.now().astimezone(datetime_timezone.utc).isoformat(),
            "duration_seconds": round(
                self.run.duration_seconds
                if self.run.duration_seconds is not None
                else monotonic() - self.started,
                3,
            ),
            "progress": self.run.progress,
        }
        if self.run.error:
            payload["error"] = self.run.error
        level = (
            logging.ERROR
            if self.run.status == LoaderRun.Status.FAILED
            else (
                logging.WARNING if self.run.status == LoaderRun.Status.INTERRUPTED else logging.INFO
            )
        )
        payload["level"] = logging.getLevelName(level)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        logger.log(
            level,
            line,
            exc_info=event == "finished" and sys.exc_info()[0] is not None,
            extra={"event_data": payload, "console_event": True},
        )
        if self.verbosity and not context_fields()["task_id"]:
            self.stream.write(line + "\n")
            self.stream.flush()

    def finish(self, status, error=""):
        now = timezone.now()
        self.run.status = status
        self.run.error = error[:ERROR_LIMIT]
        self.run.duration_seconds = monotonic() - self.started
        # Do not overwrite an interruption already recovered by another session.
        updated = LoaderRun.objects.filter(pk=self.run.pk, status=LoaderRun.Status.RUNNING).update(
            status=status,
            error=self.run.error,
            finished_at=now,
            updated_at=now,
            duration_seconds=self.run.duration_seconds,
            progress=self.run.progress,
        )
        if not updated:
            self.run.refresh_from_db()
        self.emit("finished")


def report_progress(phase, processed=0, total=None, *, deferred=0, item=None):
    reporter = _current.get()
    if reporter is None:
        return
    progress = {
        "phase": phase,
        "processed": processed,
        "total": total,
        "deferred": deferred,
        "item": item,
    }
    if total is not None:
        progress["remaining"] = max(0, total - processed)
    previous_phase = reporter.run.progress.get("phase")
    reporter.run.progress = progress
    now = monotonic()
    if (
        previous_phase != phase
        or processed == 0
        or processed == total
        or now - reporter.last_progress >= PROGRESS_INTERVAL_SECONDS
    ):
        LoaderRun.objects.filter(pk=reporter.run.pk).update(
            progress=progress, updated_at=timezone.now()
        )
        reporter.last_progress = now
        reporter.emit("progress")


@contextmanager
def loader_execution(command, scope, stream, verbosity=1):
    if connection.vendor != "postgresql":
        raise CommandError("Loader coordination requires PostgreSQL")
    if connection.in_atomic_block:
        raise CommandError("Run loader commands outside an enclosing database transaction")
    with connection.cursor() as cursor:
        for model in (LoaderRun, LoaderScheduleState):
            cursor.execute("SELECT to_regclass(%s)", [model._meta.db_table])
            if cursor.fetchone()[0] is None:
                raise CommandError(
                    "Loader run table is missing; run python manage.py migrate first"
                )
        if _current.get() is None:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [LOCK_NAMESPACE, LOCK_RESOURCE])
            acquired = cursor.fetchone()[0]
        else:
            acquired = False
    held_connection = connection.connection
    token = None
    try:
        if not acquired:
            reason = "Another loader holds the shared write lock; retry later"
            record_skipped(command, scope, stream, verbosity, reason)
            raise LoaderBusy(reason)
        control, _ = LoaderScheduleState.objects.get_or_create(key=SCHEDULE_STATE_KEY)
        if control.cooldown_until and control.cooldown_until > timezone.now():
            reason = f"NHL cooldown active until {control.cooldown_until.isoformat()}"
            record_skipped(
                command,
                scope,
                stream,
                verbosity,
                reason,
                {"next_retry_at": control.cooldown_until.isoformat()},
            )
            raise LoaderCooldown(reason)
        # Holding the lock proves no cooperating loader is still running. A hard
        # process exit may have committed data but failed to record its outcome.
        for abandoned in LoaderRun.objects.filter(status=LoaderRun.Status.RUNNING):
            now = timezone.now()
            abandoned.status = LoaderRun.Status.INTERRUPTED
            abandoned.finished_at = now
            abandoned.updated_at = now
            abandoned.duration_seconds = (now - abandoned.started_at).total_seconds()
            abandoned.error = "Previous session ended without recording its outcome; earlier writes may be committed"
            abandoned.save(
                update_fields=["status", "finished_at", "updated_at", "duration_seconds", "error"]
            )
            RunReporter(abandoned, stream, verbosity).emit("recovered")
        run = LoaderRun.objects.create(
            command=command, scope=scope, status=LoaderRun.Status.RUNNING, updated_at=timezone.now()
        )
        reporter = RunReporter(run, stream, verbosity)
        token = _current.set(reporter)

        def same_session(execute, sql, params, many, context):
            if connection.connection is not held_connection or held_connection.closed:
                raise LoaderSessionLost(
                    "Loader database session changed; refusing to continue without its lock"
                )
            return execute(sql, params, many, context)

        with bind_context(run_id=str(run.pk), command=command, scope=scope):
            reporter.emit("started")
            try:
                with connection.execute_wrapper(same_session):
                    yield reporter
            except BaseException as error:
                status = (
                    LoaderRun.Status.FAILED
                    if isinstance(error, Exception)
                    else LoaderRun.Status.INTERRUPTED
                )
                # Leave a running row for takeover recovery if even status persistence
                # is unavailable; logging failure must not mask the loader exception.
                try:
                    until = note_rate_limit(error)
                    if until is not None:
                        reporter.run.progress["next_retry_at"] = until.isoformat()
                    reporter.finish(status, f"{type(error).__name__}: {error}")
                except DatabaseError:
                    logger.exception("Could not persist loader failure for %s", run.pk)
                raise
            else:
                reporter.finish(LoaderRun.Status.SUCCEEDED)
    finally:
        if token is not None:
            _current.reset(token)
        if acquired and connection.connection is held_connection and not held_connection.closed:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(%s, %s)", [LOCK_NAMESPACE, LOCK_RESOURCE]
                    )
            except DatabaseError:
                connection.close()
                logger.exception("Loader unlock failed; closed its database session")


class LoaderCommand(BaseCommand):
    def writes_loader_data(self, options):
        return True

    def execute(self, *args, **options):
        if not self.writes_loader_data(options):
            return super().execute(*args, **options)
        command = type(self).__module__.rsplit(".", 1)[-1]
        scope = json.loads(
            json.dumps(
                {name: options[name] for name in SCOPE_OPTIONS if options.get(name) is not None},
                default=str,
            )
        )
        stream = options.get("stderr") or self.stderr
        with loader_execution(command, scope, stream, options.get("verbosity", 1)):
            return super().execute(*args, **options)
