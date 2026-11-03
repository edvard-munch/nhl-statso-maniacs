"""Required game JSON responses must fail visibly rather than become empty data."""

from datetime import date
from unittest.mock import Mock

import pytest
import requests
from django.core.management.base import CommandError

from players.management.commands import upd_gms


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    delay = Mock()
    monkeypatch.setattr(upd_gms, "sleep", delay)
    return delay


@pytest.fixture
def boxscore():
    return {"gameState": "FUT", "awayTeam": {"id": 1}, "homeTeam": {"id": 7}}


def test_boxscore_success_uses_supplied_session_and_timeout(requests_mock, boxscore):
    url = upd_gms.URL_BOXSCORE.format(2026020001)
    requests_mock.get(url, json=boxscore)
    with requests.Session() as session:
        client = Mock(wraps=session)
        assert upd_gms.get_game_data(2026020001, upd_gms.URL_BOXSCORE, client) == boxscore
    client.get.assert_called_once_with(url, timeout=upd_gms.JSON_FETCH_TIMEOUT)
    assert requests_mock.call_count == 1


@pytest.mark.parametrize(
    "failure",
    [
        {"text": ""},
        {"text": "<html>Bad gateway</html>"},
        {"status_code": 503},
        {"status_code": 429},
        {"exc": requests.ReadTimeout},
        {"exc": requests.ConnectionError},
    ],
)
def test_transient_failure_recovers_without_returning_empty_data(
    requests_mock, boxscore, no_retry_wait, failure
):
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020001), [failure, {"json": boxscore}])
    assert upd_gms.get_game_data(2026020001, upd_gms.URL_BOXSCORE) == boxscore
    assert requests_mock.call_count == 2
    no_retry_wait.assert_called_once_with(upd_gms.JSON_RETRY_DELAY)
    assert all(
        request.timeout == upd_gms.JSON_FETCH_TIMEOUT for request in requests_mock.request_history
    )


@pytest.mark.parametrize(
    "failure",
    [
        {"text": ""},
        {"text": "<html>Error</html>"},
        {"status_code": 500},
        {"status_code": 408},
        {"status_code": 429},
        {"exc": requests.ConnectTimeout},
        {"exc": requests.ConnectionError},
        {"json": None},
        {"json": []},
        {"json": {"message": "unavailable"}},
    ],
)
def test_required_response_failure_is_bounded_and_identifies_endpoint(
    requests_mock, no_retry_wait, failure
):
    url = upd_gms.URL_BOXSCORE.format(2026020001)
    requests_mock.get(url, **failure)
    with pytest.raises(CommandError) as error:
        upd_gms.get_game_data(2026020001, upd_gms.URL_BOXSCORE)
    assert url in str(error.value)
    assert "game 2026020001" in str(error.value)
    assert "after 3 attempt(s)" in str(error.value)
    assert requests_mock.call_count == upd_gms.JSON_FETCH_ATTEMPTS
    assert no_retry_wait.call_count == upd_gms.JSON_FETCH_ATTEMPTS - 1


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_http_error_does_not_retry(requests_mock, no_retry_wait, status):
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020001), status_code=status)
    with pytest.raises(CommandError, match="after 1 attempt"):
        upd_gms.get_game_data(2026020001, upd_gms.URL_BOXSCORE)
    assert requests_mock.call_count == 1
    no_retry_wait.assert_not_called()


@pytest.mark.parametrize("template", [upd_gms.URL_RIGHT_RAIL, upd_gms.URL_PLAY_BY_PLAY])
def test_supplemental_json_failure_is_not_treated_as_missing_stats(requests_mock, template):
    requests_mock.get(template.format(2026020001), text="<html>Unavailable</html>")
    with pytest.raises(CommandError, match="game 2026020001"):
        upd_gms.get_game_data(2026020001, template)


def test_valid_empty_supplemental_object_preserves_existing_fallback(requests_mock):
    requests_mock.get(upd_gms.URL_RIGHT_RAIL.format(2026020001), json={})
    assert all(value is None for value in upd_gms.get_game_report_links(2026020001).values())
    assert requests_mock.call_count == 1


def test_schedule_uses_the_same_checked_json_boundary(requests_mock):
    day = date(2026, 11, 21)
    url = upd_gms.URL_SCHEDULE.format(day)
    payload = {
        "gameWeek": [],
        "regularSeasonStartDate": "2026-10-01",
        "regularSeasonEndDate": "2027-04-20",
    }
    requests_mock.get(url, [{"status_code": 502}, {"json": payload}])
    assert upd_gms.get_schedule(day) == payload
    assert requests_mock.call_count == 2


def test_invalid_schedule_names_date_and_missing_fields(requests_mock):
    requests_mock.get(upd_gms.URL_SCHEDULE.format("2026-11-21"), json={})
    with pytest.raises(CommandError, match="schedule for 2026-11-21") as error:
        upd_gms.get_schedule("2026-11-21")
    assert "Missing required fields" in str(error.value)
