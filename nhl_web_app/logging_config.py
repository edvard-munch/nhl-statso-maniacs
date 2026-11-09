"""Shared JSON logging for Django commands and Celery, with scoped correlation."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import logging
from pathlib import Path
from time import monotonic

from django.core.exceptions import ImproperlyConfigured

ERROR_LIMIT = 2000
DURATION_PRECISION = 3
_context = ContextVar("nhl_logging_context", default={})
logger = logging.getLogger("players.tasks")


def context_fields():
    from celery import current_task

    request = getattr(current_task, "request", None)
    return {
        "task_id": getattr(request, "id", None),
        "task_name": getattr(current_task, "name", None),
        **_context.get(),
    }


@contextmanager
def bind_context(**fields):
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "process_id": record.process,
            **context_fields(),
            **getattr(record, "event_data", {}),
        }
        if not hasattr(record, "event_data"):
            payload["message"] = record.getMessage()
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleEvents(logging.Filter):
    def filter(self, record):
        # Standalone commands already emit these events to their explicit stderr
        # stream (respecting --verbosity); tasks use the configured logger only.
        return not (getattr(record, "console_event", False) and not context_fields()["task_id"])


def configuration(base_dir, destination="file"):
    if destination not in {"file", "console"}:
        raise ImproperlyConfigured("NHL_LOG_DESTINATION must be file or console")
    handler = {"level": "INFO", "formatter": "json"}
    if destination == "file":
        handler.update(
            {
                "class": "logging.handlers.WatchedFileHandler",
                "filename": str(Path(base_dir) / "logs" / "nhl_web_app.log"),
                "encoding": "utf-8",
                "delay": True,
            }
        )
    else:
        handler.update({"class": "logging.StreamHandler", "filters": ["console_events"]})
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": JsonFormatter}},
        "filters": {"console_events": {"()": ConsoleEvents}},
        "handlers": {"application": handler},
        "root": {"handlers": ["application"], "level": "WARNING"},
        "loggers": {
            name: {"handlers": [], "level": "INFO", "propagate": True}
            for name in (
                "players",
                "django",
                "celery",
                "celery.task",
                "celery.redirected",
                "multiprocessing",
            )
        },
    }


def logged_task(job):
    """Log application task lifecycles without serializing arguments/results."""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            started = monotonic()
            with bind_context(job=job):
                logger.info("Task started", extra={"event_data": {"event": "task_started"}})
                try:
                    result = function(*args, **kwargs)
                except BaseException as error:
                    interrupted = not isinstance(error, Exception)
                    logger.log(
                        logging.WARNING if interrupted else logging.ERROR,
                        "Task failed",
                        exc_info=True,
                        extra={
                            "event_data": {
                                "event": "task_finished",
                                "status": "interrupted" if interrupted else "failed",
                                "duration_seconds": round(
                                    monotonic() - started, DURATION_PRECISION
                                ),
                                "error": f"{type(error).__name__}: {error}"[:ERROR_LIMIT],
                            }
                        },
                    )
                    raise
                details = {
                    key: result[key]
                    for key in ("status", "reason")
                    if isinstance(result, dict) and key in result
                }
                logger.info(
                    "Task finished",
                    extra={
                        "event_data": {
                            "event": "task_finished",
                            "status": "succeeded",
                            **details,
                            "duration_seconds": round(monotonic() - started, DURATION_PRECISION),
                        }
                    },
                )
                return result

        return wrapped

    return decorate
