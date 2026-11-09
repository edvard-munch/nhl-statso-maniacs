from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.signals import setup_logging

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nhl_web_app.settings")

app = Celery("nhl_web_app")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print("Request: {0!r}".format(self.request))


@setup_logging.connect
def configure_worker_logging(**kwargs):
    """Keep worker/Beat and Django handlers identical, including prefork children."""
    from logging.config import dictConfig
    from django.conf import settings
    from celery.utils.log import get_multiprocessing_logger

    # Billiard initially disables propagation; initialize it before dictConfig
    # so pool-process warnings use the same destination as the worker.
    get_multiprocessing_logger()
    dictConfig(settings.LOGGING)
