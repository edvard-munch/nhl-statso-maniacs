from celery import shared_task
from django.core import management

from nhl_web_app.logging_config import logged_task

from . import scheduler


@shared_task
@logged_task("legacy")
def upd_database():
    """Legacy manual task; keep its original order and failure semantics."""
    management.call_command("upd_tms")
    management.call_command("upd_pls")
    management.call_command("upd_gms")


@shared_task
@logged_task("discovery")
def discover_games():
    return scheduler.run("discovery", scheduler.discover)


@shared_task
@logged_task("live")
def refresh_live_games():
    return scheduler.run("live", scheduler.refresh_group)


@shared_task
@logged_task("final")
def refresh_final_games():
    return scheduler.run("final", lambda: scheduler.refresh_group(final=True))


@shared_task
@logged_task("maintenance")
def refresh_daily():
    return scheduler.run("maintenance", scheduler.maintenance)


@shared_task
@logged_task("maintenance")
def refresh_teams():
    return scheduler.run("maintenance", lambda: scheduler.maintenance(teams_only=True))


@shared_task
@logged_task("cleanup")
def cleanup_history():
    return scheduler.run("cleanup", scheduler.cleanup)
