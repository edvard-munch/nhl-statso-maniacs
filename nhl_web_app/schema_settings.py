"""Canonical tooling settings for schema export; never a server configuration."""

import os

# Set these before base settings import environ or create logging directories.
# export_openapi starts a fresh process with only platform environment inherited.
os.environ.update(
    NHL_READ_ENV_FILE="false",
    DEBUG="false",
    SECRET_KEY="offline-schema-only",
    ALLOWED_HOSTS="localhost,testserver",
    POSTGRES_DB="schema-unused",
    POSTGRES_USER="schema-unused",
    POSTGRES_DB_PASSWORD="unused",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST_USER="schema@example.invalid",
    EMAIL_PASSWORD="unused",
    DEFAULT_FROM_EMAIL="schema@example.invalid",
    PASSWORD_RESET_PUBLIC_ORIGIN="",
    PASSWORD_RESET_FRONTEND_PATH="",
    STATIC_URL="/static/",
    MEDIA_URL="/media/",
    NHL_LOG_DESTINATION="console",
    NHL_SCHEDULING_ENABLED="false",
    CELERY_BROKER_URL="",
)

from .settings import *  # noqa: E402, F403 -- import the real API policy after isolation

DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
TIME_ZONE = "UTC"
