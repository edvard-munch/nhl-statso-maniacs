from types import SimpleNamespace

import pytest
import requests
from django.core.management.base import CommandError

from players.management.commands import upd_pls, upd_tms


pytestmark = pytest.mark.unit


def test_import_team_create_sets_defaults_and_uploads_logo_when_missing(monkeypatch):
    team_payload = {
        "id": 1,
        "name": {"default": "Anaheim Ducks"},
        "abbrev": "ANA",
        "firstYearOfPlay": "1993",
    }
    fake_team_obj = SimpleNamespace(slug="anaheim-ducks", abbr="ANA", image=object())
    update_calls = []
    pic_missing_calls = []
    upload_calls = []

    def fake_update_or_create(**kwargs):
        update_calls.append(kwargs)
        return fake_team_obj, True

    monkeypatch.setattr(
        upd_tms.Team,
        "objects",
        SimpleNamespace(update_or_create=fake_update_or_create),
    )

    def fake_pic_missing(img_name, field, directory):
        pic_missing_calls.append((img_name, field, directory))
        return True

    def fake_upload_pic(directory, object_, img_name, url):
        upload_calls.append((directory, object_, img_name, url))

    monkeypatch.setattr(upd_tms.upd_pls, "pic_missing", fake_pic_missing)
    monkeypatch.setattr(upd_tms.upd_pls, "upload_pic", fake_upload_pic)

    upd_tms.import_team(team_payload)

    assert update_calls == [
        {
            "nhl_id": 1,
            "defaults": {
                "name": "Anaheim Ducks",
                "abbr": "ANA",
                "nhl_debut": "1993",
            },
        }
    ]
    assert pic_missing_calls == [("anaheim-ducks.svg", fake_team_obj.image, upd_tms.TEAMS_LOGOS_DIR)]
    assert upload_calls == [
        (
            upd_tms.TEAMS_LOGOS_DIR,
            fake_team_obj,
            "anaheim-ducks.svg",
            upd_tms.URL_TEAMS_LOGOS,
        )
    ]


def test_import_team_update_skips_logo_upload_when_logo_present(monkeypatch):
    team_payload = {
        "id": 1,
        "name": {"default": "Anaheim Ducks"},
        "abbrev": "ANA",
    }
    fake_team_obj = SimpleNamespace(slug="anaheim-ducks", abbr="ANA", image=object())
    update_calls = []
    upload_calls = []

    def fake_update_or_create(**kwargs):
        update_calls.append(kwargs)
        return fake_team_obj, False

    monkeypatch.setattr(
        upd_tms.Team,
        "objects",
        SimpleNamespace(update_or_create=fake_update_or_create),
    )
    monkeypatch.setattr(upd_tms.upd_pls, "pic_missing", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        upd_tms.upd_pls,
        "upload_pic",
        lambda *args, **kwargs: upload_calls.append((args, kwargs)),
    )

    upd_tms.import_team(team_payload)

    assert update_calls == [{"nhl_id": 1, "defaults": {"name": "Anaheim Ducks", "abbr": "ANA"}}]
    assert upload_calls == []


def test_get_response_returns_teams_from_api(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"teams": [{"id": 1}, {"id": 2}]}

    monkeypatch.setattr(upd_tms.requests, "get", lambda url: FakeResponse())

    assert upd_tms.get_response() == [{"id": 1}, {"id": 2}]


def test_get_response_raises_command_error_on_connection_error(monkeypatch):
    def raise_connection_error(url):
        raise requests.exceptions.ConnectionError("network down")

    monkeypatch.setattr(upd_tms.requests, "get", raise_connection_error)

    with pytest.raises(CommandError, match="CONNECTION COULD NOT BE ESTABLISHED"):
        upd_tms.get_response()


@pytest.mark.parametrize(
    "player, field, expected",
    [
        ({"wins": None}, "wins", 0),
        ({"wins": 12}, "wins", 12),
    ],
)
def test_get_num_field_value(player, field, expected):
    assert upd_pls.get_num_field_value(player, field) == expected


def test_get_country_name_returns_known_country():
    assert upd_pls.get_country_name("POL") == "Poland"


def test_get_country_name_returns_unknown_code_and_logs_once(monkeypatch):
    warnings = []
    upd_pls.UNKNOWN_COUNTRY_CODES.clear()

    monkeypatch.setattr(upd_pls.logger, "warning", lambda message, code: warnings.append((message, code)))

    assert upd_pls.get_country_name("XXX") == "XXX"
    assert upd_pls.get_country_name("XXX") == "XXX"
    assert warnings == [("Unknown country code from NHL API: %s", "XXX")]
    upd_pls.UNKNOWN_COUNTRY_CODES.clear()


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0, "00:00"),
        (61, "01:01"),
        (600, "10:00"),
    ],
)
def test_time_from_sec(seconds, expected):
    assert upd_pls.time_from_sec(seconds) == expected


def test_get_season_id_returns_single_detected_season(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"teams": [{"seasonId": 20252026}, {"seasonId": 20252026}]}

    monkeypatch.setattr(upd_pls.requests, "get", lambda *args, **kwargs: FakeResponse())

    assert upd_pls.get_season_id() == "20252026"


def test_get_season_id_returns_latest_when_multiple_seasons(monkeypatch):
    warnings = []

    class FakeResponse:
        def json(self):
            return {"teams": [{"seasonId": 20242025}, {"seasonId": 20252026}]}

    monkeypatch.setattr(upd_pls.requests, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(upd_pls.logger, "warning", lambda message, *args: warnings.append((message, args)))

    assert upd_pls.get_season_id() == "20252026"
    assert warnings[0][0] == "Multiple seasonId values from NHL schedule API (%s), using %s"


def test_get_season_id_falls_back_to_default_on_request_exception(monkeypatch):
    def raise_request_exception(*args, **kwargs):
        raise requests.exceptions.RequestException("timeout")

    monkeypatch.setattr(upd_pls.requests, "get", raise_request_exception)

    assert upd_pls.get_season_id() == upd_pls.DEFAULT_SEASON
