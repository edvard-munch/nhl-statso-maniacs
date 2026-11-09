"""Validated, opt-in schedules; importing settings never starts a scheduler."""

from urllib.parse import urlsplit

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

LIVE_QUEUE = "nhl-live"
MAINTENANCE_QUEUE = "nhl-maintenance"
SECONDS_PER_DAY = 86400
MIN_INTERVAL = 60
INTERVAL_DEFAULTS = {
    "live_seconds": 300,
    "discovery_seconds": 300,
    "quiet_discovery_seconds": 1800,
    "final_seconds": 600,
    "maintenance_seconds": 900,
    "final_window_seconds": 3600,
    "pre_game_seconds": 3600,
    "cooldown_seconds": 300,
}


def read_options(env):
    options = {"enabled": env("NHL_SCHEDULING_ENABLED", cast=bool, default=False)}
    for name, default in INTERVAL_DEFAULTS.items():
        value = env("NHL_" + name.upper(), cast=int, default=default)
        if not MIN_INTERVAL <= value <= SECONDS_PER_DAY:
            raise ImproperlyConfigured(
                f"NHL_{name.upper()} must be between {MIN_INTERVAL} and {SECONDS_PER_DAY}"
            )
        options[name] = value
    for name, default, minimum, maximum in (
        ("quiet_start_hour", 9, 0, 23),
        ("quiet_hours", 3, 1, 24),
        ("weekly_weekday", 0, 0, 6),
        ("recent_days", 3, 1, 7),
        ("run_retention_days", 30, 1, 3650),
    ):
        value = env("NHL_" + name.upper(), cast=int, default=default)
        if not minimum <= value <= maximum:
            raise ImproperlyConfigured(
                f"NHL_{name.upper()} must be between {minimum} and {maximum}"
            )
        options[name] = value
    return options


def beat_schedule(options, broker_url):
    if not options["enabled"]:
        return {}
    broker = urlsplit(broker_url)
    if broker.scheme not in {"amqp", "amqps"} or not broker.hostname:
        raise ImproperlyConfigured(
            "Scheduling requires an explicit RabbitMQ amqp(s) CELERY_BROKER_URL"
        )
    schedule = {}
    for name, task, interval, queue in (
        ("nhl-discovery", "discover_games", options["discovery_seconds"], LIVE_QUEUE),
        ("nhl-live", "refresh_live_games", options["live_seconds"], LIVE_QUEUE),
        ("nhl-final", "refresh_final_games", options["final_seconds"], LIVE_QUEUE),
        ("nhl-daily", "refresh_daily", options["maintenance_seconds"], MAINTENANCE_QUEUE),
        ("nhl-weekly", "refresh_teams", options["maintenance_seconds"], MAINTENANCE_QUEUE),
    ):
        schedule[name] = {
            "task": "players.tasks." + task,
            "schedule": float(interval),
            "options": {"queue": queue, "expires": interval},
        }
    schedule["nhl-history-cleanup"] = {
        "task": "players.tasks.cleanup_history",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": MAINTENANCE_QUEUE, "expires": options["maintenance_seconds"]},
    }
    # Celery checks this entry key (not its task value) before installing its
    # own default cleanup on the otherwise-unconsumed default queue.
    schedule["celery.backend_cleanup"] = {
        "task": "celery.backend_cleanup",
        "schedule": crontab(hour=4, minute=15),
        "options": {"queue": MAINTENANCE_QUEUE, "expires": options["maintenance_seconds"]},
    }
    return schedule


TASK_ROUTES = {
    **{
        "players.tasks." + name: {"queue": LIVE_QUEUE}
        for name in ("discover_games", "refresh_live_games", "refresh_final_games")
    },
    **{
        "players.tasks." + name: {"queue": MAINTENANCE_QUEUE}
        for name in ("refresh_daily", "refresh_teams", "cleanup_history", "upd_database")
    },
    "celery.backend_cleanup": {"queue": MAINTENANCE_QUEUE},
}
