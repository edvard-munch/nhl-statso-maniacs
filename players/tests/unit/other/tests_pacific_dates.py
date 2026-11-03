"""The calendar date used by the UI and game loader must stay in US Pacific time."""

from datetime import datetime, timezone

import pytest
from django.core.management.base import CommandError

from players import utils
from players.management.commands import upd_gms


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "instant, expected",
    [
        ("2026-01-01T07:59:00", "2025-12-31"),
        ("2026-01-01T08:00:00", "2026-01-01"),
        ("2026-07-01T06:59:00", "2026-06-30"),
        ("2026-07-01T07:00:00", "2026-07-01"),
    ],
)
@pytest.mark.parametrize("consumer", ["ui", "game_loader"])
def test_pacific_midnight_in_standard_and_daylight_time(monkeypatch, instant, expected, consumer):
    moment = datetime.fromisoformat(instant).replace(tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz)

    if consumer == "ui":
        monkeypatch.setattr(utils.datetime, "datetime", FrozenDateTime)
        assert utils.get_us_pacific_date() == expected
    else:
        monkeypatch.setattr(upd_gms, "datetime", FrozenDateTime)
        requested_dates = []

        def schedule(day, session):
            requested_dates.append(day.isoformat())
            # Stop before any HTTP requests or ORM reads/writes.
            raise CommandError("synthetic date checkpoint")

        monkeypatch.setattr(upd_gms, "get_schedule", schedule)
        with pytest.raises(CommandError, match="synthetic date checkpoint"):
            upd_gms.Command().handle()
        assert requested_dates == [expected]
