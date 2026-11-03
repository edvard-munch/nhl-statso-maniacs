"""Offline request contracts independent of the configured fallback season."""

import json
from copy import deepcopy

import pytest

from players.management.commands import upd_pls


pytestmark = pytest.mark.unit


@pytest.fixture(params=["20242025", "20262027"])
def report_season(request, monkeypatch):
    params = deepcopy(upd_pls.REQUEST_PARAMS)
    params["cayenneExp"] = "gameTypeId=2 and seasonId={}".format(request.param)
    # get_response mutates start; keep both the season and pagination local.
    monkeypatch.setattr(upd_pls, "REQUEST_PARAMS", params)
    return request.param


@pytest.mark.parametrize("start", [0, 100])
def test_get_response_goalies_bios(requests_mock, report_season, start):
    payload = {"data": [{"playerId": 9000001, "goalieFullName": "Fixture Goalie"}], "total": 1}
    endpoint = "https://api.nhle.com/stats/rest/en/goalie/bios"
    requests_mock.get(endpoint, json=payload)

    response = upd_pls.get_response("bios", "goalie", start)

    assert response.status_code == 200
    assert response.json() == payload
    assert requests_mock.call_count == 1
    request = requests_mock.last_request
    assert request.qs["cayenneexp"] == [
        "gameTypeId=2 and seasonId={}".format(report_season).lower()
    ]
    assert request.qs["start"] == [str(start)]
    assert request.qs["limit"] == ["100"]
    assert request.qs["isaggregate"] == request.qs["isgame"] == ["false"]
    # Query whitespace and parameter order are not part of the request contract.
    assert json.loads(request.qs["sort"][0]) == [
        {"property": "lastname", "direction": "asc_ci"},
        {"property": "playerid", "direction": "asc_ci"},
    ]
    assert request.timeout == upd_pls.TIMEOUT


def test_no_response_goalies_bios(requests_mock, report_season):
    requests_mock.get("https://api.nhle.com/stats/rest/en/goalie/bios", status_code=401)

    response = upd_pls.get_response("bios", "goalie", 0)

    assert response.status_code == 401
    assert requests_mock.call_count == 1
    assert requests_mock.last_request.qs["cayenneexp"] == [
        "gameTypeId=2 and seasonId={}".format(report_season).lower()
    ]
