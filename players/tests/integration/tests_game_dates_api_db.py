"""Bounded saved-date navigation over synthetic gamedays, without upstream I/O."""

from datetime import date, datetime, timedelta, timezone as utc
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
import pytest

from players.api import game_dates
from players.models import Game, Gameday

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
NOW = datetime(2026, 10, 11, 12, tzinfo=utc.utc)


@pytest.fixture(autouse=True)
def offline(requests_mock, monkeypatch):
    monkeypatch.setattr(game_dates.timezone, "now", lambda: NOW)
    return requests_mock


@pytest.fixture
def days():
    dates = [date(2026, 10, 1) + timedelta(days=index * 2) for index in range(12)]
    Gameday.objects.bulk_create([Gameday(day=day) for day in reversed(dates)])
    return dates


def get(client, **params):
    return client.get(reverse("api_v1:game-dates"), params)


def test_public_response_is_read_only_bounded_and_includes_saved_days_without_games(
    client, days, offline
):
    with CaptureQueriesContext(connection) as queries:
        response = get(client)
    assert response.status_code == 200, response.content
    assert response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"]
    assert len(queries) == 6
    assert all(item["sql"].lstrip().startswith("SELECT") for item in queries)
    data = response.json()
    assert data["count"] == 12
    assert data["next"] is data["previous"] is None
    assert data["results"] == [{"date": day.isoformat()} for day in reversed(days)]
    assert data["meta"] == {
        "requested_date": None,
        "reference_date": "2026-10-11",
        "schedule_timezone": "America/Los_Angeles",
        "latest_date": "2026-10-23",
        "selected_date": "2026-10-11",
        "used_fallback": False,
        "previous_date": "2026-10-09",
        "next_date": "2026-10-13",
        "window": [day.isoformat() for day in days[2:8]],
    }
    assert Gameday.objects.count() == 12 and Game.objects.count() == 0
    assert not offline.called


@pytest.mark.parametrize("index", [0, 1, 2, 3, 6, 9, 10, 11])
def test_window_fills_both_edges_and_neighbors_skip_unsaved_days(client, days, index):
    meta = get(client, date=days[index].isoformat()).json()["meta"]
    start = min(max(index - 3, 0), 6)
    assert meta["window"] == [day.isoformat() for day in days[start : start + 6]]
    assert meta["requested_date"] == meta["selected_date"] == days[index].isoformat()
    assert meta["used_fallback"] is False
    assert meta["previous_date"] == (days[index - 1].isoformat() if index else None)
    assert meta["next_date"] == (days[index + 1].isoformat() if index < 11 else None)


@pytest.mark.parametrize("reference", ["1900-01-01", "2026-10-02", "2099-12-31"])
def test_unsaved_reference_explicitly_falls_back_to_latest_without_altering_scoreboard(
    client, days, reference
):
    meta = get(client, date=reference).json()["meta"]
    assert meta["requested_date"] == meta["reference_date"] == reference
    assert meta["selected_date"] == meta["latest_date"] == days[-1].isoformat()
    assert meta["used_fallback"] is True
    assert meta["next_date"] is None
    board = client.get(reverse("api_v1:games"), {"date": reference}).json()
    assert board["count"] == 0 and board["meta"]["date"] == reference


def test_pagination_does_not_change_navigation_or_reference(client, days):
    params = {"date": days[1].isoformat(), "page_size": 2}
    first = get(client, **params).json()
    second = get(client, page=2, **params).json()
    assert first["meta"] == second["meta"]
    assert second["results"] == [{"date": day.isoformat()} for day in reversed(days[8:10])]
    query = parse_qs(urlparse(second["next"]).query)
    assert query == {"date": [days[1].isoformat()], "page_size": ["2"], "page": ["3"]}
    assert get(client, page=7, **params).status_code == 404


@pytest.mark.parametrize("reference", [None, "2026-10-11"])
def test_empty_store_has_no_selection_and_no_fallback_or_writes(
    client, django_assert_num_queries, reference
):
    with django_assert_num_queries(1):
        response = get(client, **({"date": reference} if reference else {}))
    data = response.json()
    assert response.status_code == 200
    assert data["count"] == 0 and data["results"] == []
    assert data["meta"]["requested_date"] == reference
    assert data["meta"]["reference_date"] == "2026-10-11"
    assert data["meta"]["selected_date"] is data["meta"]["latest_date"] is None
    assert data["meta"]["previous_date"] is data["meta"]["next_date"] is None
    assert data["meta"]["window"] == [] and data["meta"]["used_fallback"] is False
    assert get(client, page=2).status_code == 404
    assert not Gameday.objects.exists()


@pytest.mark.parametrize("dates", [["2026-10-01"], ["2026-10-01", "2026-10-05"]])
def test_short_window_never_invents_dates(client, dates):
    Gameday.objects.bulk_create([Gameday(day=day) for day in dates])
    meta = get(client, date=dates[0]).json()["meta"]
    assert meta["window"] == dates
    assert meta["previous_date"] is None
    assert meta["next_date"] == (dates[1] if len(dates) > 1 else None)


@pytest.mark.parametrize(
    "instant, expected",
    [
        (datetime(2026, 11, 1, 6, 30, tzinfo=utc.utc), "2026-10-31"),
        (datetime(2026, 11, 1, 8, 30, tzinfo=utc.utc), "2026-11-01"),
        (datetime(2026, 11, 1, 9, 30, tzinfo=utc.utc), "2026-11-01"),
    ],
)
def test_default_reference_uses_pacific_schedule_date_across_dst(
    client, monkeypatch, settings, instant, expected
):
    settings.TIME_ZONE = "Asia/Tokyo"
    monkeypatch.setattr(game_dates.timezone, "now", lambda: instant)
    Gameday.objects.create(day=expected)
    meta = get(client).json()["meta"]
    assert meta["reference_date"] == meta["selected_date"] == expected
    assert meta["used_fallback"] is False


@pytest.mark.parametrize(
    "query",
    [
        "date=",
        "date=2026-2-01",
        "date=2026-02-30",
        "date=2026-11-01T00:00:00Z",
        "date=2026-10-01&date=2026-10-03",
        "season_id=20262027",
        "page=0",
        "page_size=101",
        "page_size=all",
        "page=1&page=2",
        "ordering=day",
    ],
)
def test_invalid_query_is_json_400_without_database_access(
    client, django_assert_num_queries, query
):
    with django_assert_num_queries(0):
        response = client.get(reverse("api_v1:game-dates") + "?" + query)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameters"


def test_large_population_queries_and_payloads_are_bounded(client):
    Gameday.objects.bulk_create(
        [Gameday(day=date(2000, 1, 1) + timedelta(days=index)) for index in range(500)]
    )
    with CaptureQueriesContext(connection) as queries:
        data = get(client, date="2000-01-15", page_size=3).json()
    assert len(queries) == 6
    assert data["count"] == 500 and len(data["results"]) == 3
    assert len(data["meta"]["window"]) == 6
    selects = [item["sql"] for item in queries if "COUNT(" not in item["sql"]]
    assert all("LIMIT" in sql for sql in selects)


def test_games_do_not_duplicate_dates_and_undated_games_do_not_create_dates(client, days):
    day = Gameday.objects.get(day=days[0])
    Game.objects.create(nhl_id=1, gameday=day)
    Game.objects.create(nhl_id=2, gameday=day)
    Game.objects.create(nhl_id=3)
    before = get(client).json()
    assert before["count"] == 12
    user = get_user_model().objects.create_user(username="date-viewer")
    client.force_login(user)
    assert get(client).json() == before
    assert client.post(reverse("api_v1:game-dates"), {}).status_code == 405
