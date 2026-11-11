"""Saved gameday navigation, independent of loaders and exact-date scoreboards."""

from zoneinfo import ZoneInfo

from django.utils import timezone

from players.models import Gameday

SCHEDULE_TIMEZONE = "America/Los_Angeles"
DATE_WINDOW_SIZE = 6
DATES_BEFORE_SELECTION = DATE_WINDOW_SIZE // 2


def saved_dates():
    return Gameday.objects.order_by("-day").values("day")


def date_navigation(requested_date, count):
    reference = requested_date or timezone.now().astimezone(ZoneInfo(SCHEDULE_TIMEZONE)).date()
    meta = {
        "requested_date": requested_date,
        "reference_date": reference,
        "schedule_timezone": SCHEDULE_TIMEZONE,
        "latest_date": None,
        "selected_date": None,
        "used_fallback": False,
        "previous_date": None,
        "next_date": None,
        "window": [],
    }
    if not count:
        return meta
    days = Gameday.objects.order_by("day").values_list("day", flat=True)
    latest = days.last()
    selected = reference if days.filter(day=reference).exists() else latest
    index = days.filter(day__lt=selected).count()
    start = min(max(index - DATES_BEFORE_SELECTION, 0), max(count - DATE_WINDOW_SIZE, 0))
    window = list(days[start : start + DATE_WINDOW_SIZE])
    selected_index = window.index(selected)
    meta.update(
        latest_date=latest,
        selected_date=selected,
        used_fallback=selected != reference,
        previous_date=window[selected_index - 1] if selected_index else None,
        next_date=window[selected_index + 1] if selected_index + 1 < len(window) else None,
        window=window,
    )
    return meta
