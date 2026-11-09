from celery import shared_task
from django.core import management

from . import scheduler


@shared_task
def upd_database():
    """Legacy manual task; keep its original order and failure semantics."""
    management.call_command("upd_tms")
    management.call_command("upd_pls")
    management.call_command("upd_gms")


@shared_task
def discover_games():
    return scheduler.run("discovery", scheduler.discover)


@shared_task
def refresh_live_games():
    return scheduler.run("live", scheduler.refresh_group)


@shared_task
def refresh_final_games():
    return scheduler.run("final", lambda: scheduler.refresh_group(final=True))


@shared_task
def refresh_daily():
    return scheduler.run("maintenance", scheduler.maintenance)


@shared_task
def refresh_teams():
    return scheduler.run("maintenance", lambda: scheduler.maintenance(teams_only=True))


@shared_task
def cleanup_history():
    return scheduler.run("cleanup", scheduler.cleanup)
