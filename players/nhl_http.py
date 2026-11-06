"""One bounded GET policy for NHL loaders and their optional downloads."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import logging
from time import sleep

from django.core.management.base import CommandError
import requests

logger = logging.getLogger(__name__)
ATTEMPTS = 3
TIMEOUT = 10
BACKOFF_SECONDS = 1
RATE_LIMIT_BACKOFF_SECONDS = 5
MAX_RETRY_DELAY = 60
RATE_LIMIT_STATUS = 429
RETRYABLE_STATUSES = {408, RATE_LIMIT_STATUS}
SERVER_ERROR_STATUS = 500
TRANSIENT_ERRORS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
)


def utc_now():
    return datetime.now(timezone.utc)


def retry_after_seconds(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdigit():
            return float(value)
        deadline = parsedate_to_datetime(value)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return max(0, (deadline - utc_now()).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def get(
    url, *, session=None, timeout=TIMEOUT, attempts=ATTEMPTS, validate=None, sleep_fn=None, **kwargs
):
    """Retry one GET/validation operation; never nest independent retry budgets."""
    client = session or requests
    wait = sleep_fn if sleep_fn is not None else sleep
    for attempt in range(1, attempts + 1):
        response = None
        try:
            response = client.get(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return validate(response) if validate is not None else response
        except (requests.RequestException, ValueError) as error:
            error.attempts = attempt
            status = None
            if isinstance(error, requests.HTTPError):
                response = error.response if error.response is not None else response
                status = response.status_code if response is not None else None
                retryable = status in RETRYABLE_STATUSES or (
                    status is not None and status >= SERVER_ERROR_STATUS
                )
            else:
                retryable = isinstance(error, TRANSIENT_ERRORS) or (
                    response is not None and isinstance(error, ValueError)
                )
            retry_after = (
                retry_after_seconds(response.headers.get("Retry-After"))
                if response is not None
                else None
            )
            if response is not None:
                response.close()
            if not retryable or attempt == attempts:
                raise
            base = RATE_LIMIT_BACKOFF_SECONDS if status == RATE_LIMIT_STATUS else BACKOFF_SECONDS
            delay = max(base * 2 ** (attempt - 1), retry_after or 0)
            if delay > MAX_RETRY_DELAY:
                error.args = (
                    f"{error}; required retry delay {delay:g}s exceeds {MAX_RETRY_DELAY}s limit; retry later",
                )
                raise
            logger.warning(
                "Retrying GET %s after attempt %s/%s in %gs: %s",
                url,
                attempt,
                attempts,
                delay,
                error,
            )
            wait(delay)


def failure_message(error, context, url):
    return "Failed {} at {} after {} attempt(s): {}".format(
        context,
        url,
        getattr(error, "attempts", 1),
        error,
    )


def raise_if_rate_limited(error, context, url):
    if (
        isinstance(error, requests.HTTPError)
        and error.response is not None
        and error.response.status_code == RATE_LIMIT_STATUS
    ):
        raise CommandError(failure_message(error, context, url)) from error


def required_get(url, *, context, **kwargs):
    try:
        return get(url, **kwargs)
    except (requests.RequestException, ValueError) as error:
        raise CommandError(failure_message(error, context, url)) from error


def optional_get(url, *, context, **kwargs):
    try:
        return get(url, **kwargs)
    except requests.RequestException as error:
        raise_if_rate_limited(error, context, url)
        logger.warning("Optional %s unavailable at %s: %s", context, url, error)
        return None
