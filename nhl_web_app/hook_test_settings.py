"""Settings for the hook runner; database values have no application fallback."""

import os

from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["NHL_TEST_DB_NAME"],
        "USER": os.environ["NHL_TEST_DB_USER"],
        "PASSWORD": os.environ["NHL_TEST_DB_PASSWORD"],
        "HOST": os.environ["NHL_TEST_DB_HOST"],
        "PORT": os.environ["NHL_TEST_DB_PORT"],
        "TEST": {"NAME": os.environ.get("NHL_TEST_DB_RUN_NAME")},
    }
}
