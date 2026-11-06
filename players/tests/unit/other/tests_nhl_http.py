"""Bounded retries respect cooldowns without real HTTP calls or sleeps."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import Mock

from django.core.management.base import CommandError
import pytest
import requests
import requests_mock as http_mock

from players import nhl_http, season_loading
from players.management.commands import upd_gms, upd_pls, upd_pls_tot, upd_tms

pytestmark = pytest.mark.unit
URL = "https://api.nhle.com/stats/rest/en/skater/summary"


@pytest.fixture
def waits(monkeypatch):
    wait = Mock()
    monkeypatch.setattr(nhl_http, "sleep", wait)
    monkeypatch.setattr(upd_gms, "sleep", wait)
    return wait


@pytest.mark.parametrize(
    "header, delay",
    [
        ("12", 12),
        ("0", 5),
        (" 7 ", 7),
        (None, 5),
        ("invalid", 5),
        ("-1", 5),
        ("NaN", 5),
        ("1.5", 5),
    ],
)
def test_rate_limit_cooldown_and_fallback(requests_mock, waits, header, delay):
    headers = {} if header is None else {"Retry-After": header}
    requests_mock.get(URL, [{"status_code": 429, "headers": headers}, {"json": {"ok": True}}])
    assert nhl_http.get(URL).json() == {"ok": True}
    waits.assert_called_once_with(delay)
    assert requests_mock.call_count == 2


@pytest.mark.parametrize("offset, expected", [(17, 17), (-10, 5)])
def test_http_date_retry_after_uses_utc_clock(requests_mock, waits, monkeypatch, offset, expected):
    now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(nhl_http, "utc_now", lambda: now)
    header = format_datetime(now + timedelta(seconds=offset), usegmt=True)
    requests_mock.get(URL, [{"status_code": 429, "headers": {"Retry-After": header}}, {"json": {}}])
    nhl_http.get(URL)
    waits.assert_called_once_with(expected)


@pytest.mark.parametrize(
    "status, delays", [(429, [5, 10]), (408, [1, 2]), (500, [1, 2]), (503, [1, 2])]
)
def test_exhaustion_is_bounded_with_exponential_backoff(requests_mock, waits, status, delays):
    requests_mock.get(URL, status_code=status)
    with pytest.raises(CommandError, match="after 3 attempt"):
        nhl_http.required_get(URL, context="test report")
    assert requests_mock.call_count == 3
    assert [call.args[0] for call in waits.call_args_list] == delays


@pytest.mark.parametrize("header", ["61", "999999999999999999999999", "9" * 1000])
def test_long_server_cooldown_stops_instead_of_retrying_early(requests_mock, waits, header):
    requests_mock.get(URL, status_code=429, headers={"Retry-After": header})
    with pytest.raises(CommandError, match="retry later"):
        nhl_http.required_get(URL, context="test report")
    assert requests_mock.call_count == 1
    waits.assert_not_called()


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_http_failures_do_not_retry(requests_mock, waits, status):
    requests_mock.get(URL, status_code=status, headers={"Retry-After": "30"})
    with pytest.raises(requests.HTTPError):
        nhl_http.get(URL)
    assert requests_mock.call_count == 1
    waits.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [requests.ConnectionError, requests.ReadTimeout, requests.exceptions.ChunkedEncodingError],
)
def test_transport_failure_recovers_using_supplied_session(requests_mock, waits, error):
    requests_mock.get(URL, [{"exc": error}, {"json": {"data": []}}])
    with requests.Session() as session:
        client = Mock(wraps=session)
        params = {"start": 100, "playerId": 42}
        result = nhl_http.get(URL, session=client, params=params, timeout=7)
    assert result.json() == {"data": []}
    assert params == {"start": 100, "playerId": 42}
    assert all(
        call.kwargs == {"params": params, "timeout": 7} for call in client.get.call_args_list
    )
    waits.assert_called_once_with(1)


def test_retry_after_on_service_unavailable_is_honored(requests_mock, waits, caplog):
    requests_mock.get(URL, [{"status_code": 503, "headers": {"Retry-After": "13"}}, {"json": {}}])
    nhl_http.get(URL)
    waits.assert_called_once_with(13)
    assert "in 13s" in caplog.text and URL in caplog.text


def test_failed_response_is_closed_before_retry(waits):
    response = requests.Response()
    response.status_code = 429
    response._content = b"limited"
    response.url = URL
    response.close = Mock()
    success = Mock()
    success.raise_for_status.return_value = None
    session = Mock()
    session.get.side_effect = [response, success]
    waits.side_effect = lambda delay: response.close.assert_called_once()
    assert nhl_http.get(URL, session=session) is success


@pytest.mark.parametrize("status", [404, 503])
def test_optional_unavailable_data_remains_optional(requests_mock, waits, status):
    requests_mock.get(URL, status_code=status)
    assert nhl_http.optional_get(URL, context="optional report") is None
    assert requests_mock.call_count == (1 if status == 404 else 3)


def test_optional_rate_limit_must_stop_instead_of_hammering_next_player(requests_mock, waits):
    requests_mock.get(URL, status_code=429)
    with pytest.raises(CommandError, match="optional career"):
        nhl_http.optional_get(URL, context="optional career")
    assert requests_mock.call_count == 3


@pytest.mark.parametrize(
    "error", [requests.exceptions.InvalidURL, requests.exceptions.MissingSchema]
)
def test_invalid_urls_are_not_retried(requests_mock, waits, error):
    requests_mock.get(URL, exc=error)
    with pytest.raises(error):
        nhl_http.get(URL)
    assert requests_mock.call_count == 1
    waits.assert_not_called()


def test_http_and_json_failures_share_one_attempt_budget(requests_mock, waits):
    requests_mock.get(
        URL,
        [
            {"status_code": 429},
            {"text": "<html>Unavailable</html>"},
            {"json": {"ok": True}},
        ],
    )
    assert nhl_http.required_get(
        URL, context="JSON report", validate=lambda response: response.json()
    ) == {"ok": True}
    assert requests_mock.call_count == 3
    assert [call.args[0] for call in waits.call_args_list] == [5, 2]


@pytest.mark.parametrize(
    "kind",
    [
        "teams",
        "season",
        "player-report",
        "landing",
        "career-skater",
        "career-goalie",
        "game-json",
        "html",
        "logo",
        "profile-image",
    ],
)
def test_loader_entrypoints_share_rate_limit_recovery(
    requests_mock, waits, kind, settings, tmp_path
):
    settings.MEDIA_ROOT = str(tmp_path)
    payload = {"teams": [{"seasonId": 20262027}], "data": [], "total": 0}
    requests_mock.get(
        http_mock.ANY,
        [
            {"status_code": 429, "headers": {"Retry-After": "7"}},
            {"json": payload},
        ],
    )
    if kind == "teams":
        assert upd_tms.get_response() == payload["teams"]
    elif kind == "season":
        assert upd_pls.get_season_id() == "20262027"
    elif kind == "player-report":
        assert season_loading.fetch_report("summary", "goalie", season="20262027") == []
    elif kind == "landing":
        assert upd_pls_tot.get_response(42).json() == payload
    elif kind == "career-skater":
        assert upd_pls_tot.get_stats_rest_rows("summary", 42) == []
    elif kind == "career-goalie":
        assert upd_pls_tot.get_goalie_stats_rest_rows("summary", 42) == []
    elif kind == "game-json":
        assert upd_gms.fetch_json(URL, "test game") == payload
    elif kind == "html":
        assert upd_gms.fetch_report_html(URL)
    else:
        image = Mock()
        player = SimpleNamespace(abbr="BUF", nhl_id=42, name="Player", image=image)
        if kind == "logo":
            upd_pls.upload_pic("teams_logos", player, "buf.svg", "https://assets.nhle.com/{}.svg")
        else:
            upd_pls_tot.upload_profile_image(
                "https://assets.nhle.com/player.png", player, "player.png"
            )
        image.save.assert_called_once()
        assert image.save.call_args.kwargs["content"].read()
    assert requests_mock.call_count == 2
    waits.assert_called_once_with(7)
    assert all(request.timeout is not None for request in requests_mock.request_history)


def test_season_detection_does_not_fall_back_on_exhausted_rate_limit(requests_mock, waits):
    requests_mock.get(upd_pls.URL_SCHEDULE_CALENDAR_NOW, status_code=429)
    with pytest.raises(CommandError, match="season detection"):
        upd_pls.get_season_id()
