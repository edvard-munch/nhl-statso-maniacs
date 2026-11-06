"""Read-only smoke checks for supported team, landing and game sources."""

import re

import pytest

from players import nhl_http, season_loading
from players.management.commands import upd_gms, upd_pls_tot, upd_tms


pytestmark = [pytest.mark.integration, pytest.mark.external]


def test_calendar_team_and_season_contract(live_session):
    with nhl_http.get(upd_tms.URL_TEAMS, session=live_session) as response:
        payload = response.json()
    assert isinstance(payload, dict)
    teams = payload["teams"]
    assert isinstance(teams, list) and teams
    ids = set()
    for team in teams:
        assert {"id", "abbrev", "name", "seasonId"} <= team.keys()
        assert isinstance(team["id"], int) and team["id"] > 0
        assert team["id"] not in ids
        ids.add(team["id"])
        assert team["abbrev"] and team["name"]["default"]
        season = str(team["seasonId"])
        assert re.fullmatch(r"\d{8}", season)
        assert int(season[4:]) == int(season[:4]) + 1


def test_team_registry_reader_contract(live_session):
    teams = season_loading.fetch_team_ids(session=live_session)
    assert teams
    assert isinstance(teams["EDM"], int) and teams["EDM"] > 0
    assert isinstance(teams["TBL"], int) and teams["TBL"] > 0


def test_schedule_contract(live_reference, live_session):
    payload = upd_gms.get_schedule(live_reference["date"], session=live_session)
    assert upd_gms.SCHEDULE_FIELDS <= payload.keys()
    assert isinstance(payload["gameWeek"], list) and payload["gameWeek"]
    games = []
    for day in payload["gameWeek"]:
        assert {"date", "games"} <= day.keys()
        assert isinstance(day["games"], list)
        games.extend(day["games"])
    game = next(game for game in games if game["id"] == live_reference["game_id"])
    assert {"id", "gameType", "gameState", "awayTeam", "homeTeam"} <= game.keys()
    assert game["gameType"] == season_loading.REGULAR_SEASON
    assert game["gameState"] in upd_gms.FINAL_GAME_STATES


def test_boxscore_and_roster_reader_contract(live_reference, live_boxscore):
    assert live_boxscore["id"] == live_reference["game_id"]
    assert str(live_boxscore["season"]) == live_reference["season"]
    assert live_boxscore["gameState"] in upd_gms.FINAL_GAME_STATES
    rosters = upd_gms.get_rosters_api(live_boxscore, game_id=live_reference["game_id"])
    assert rosters
    for side in upd_gms.ROSTER_SIDES:
        assert live_boxscore[side]["abbrev"]
        assert isinstance(live_boxscore[side]["score"], int)
        assert any(rosters[side].values())


@pytest.mark.parametrize("player_type", ["skater", "goalie"])
def test_player_landing_contract(player_type, live_reference, live_session):
    player_id = live_reference["players"][player_type]
    with upd_pls_tot.get_response(player_id, session=live_session) as response:
        payload = response.json()
    assert payload["playerId"] == player_id
    assert {"firstName", "lastName", "position", "careerTotals", "seasonTotals"} <= payload.keys()
    if player_type == "goalie":
        assert payload["position"] == "G"
    else:
        assert payload["position"] != "G"
    assert isinstance(payload["careerTotals"]["regularSeason"], dict)
    assert isinstance(payload["seasonTotals"], list) and payload["seasonTotals"]


def test_play_by_play_reader_contract(live_reference, live_session):
    payload = upd_gms.get_game_data(
        live_reference["game_id"], upd_gms.URL_PLAY_BY_PLAY, session=live_session
    )
    assert payload["id"] == live_reference["game_id"]
    assert isinstance(payload["plays"], list) and payload["plays"]
    assert {"id", "abbrev"} <= payload["awayTeam"].keys()
    assert {"id", "abbrev"} <= payload["homeTeam"].keys()
    points = upd_gms.parse_special_teams_points(payload)
    assert points, "Reference game must still provide special-teams scoring events"
    assert all(isinstance(player_id, int) and stats for player_id, stats in points.items())


@pytest.mark.parametrize(
    "report, parser, fields",
    [
        ("faceoffSummary", upd_gms.parse_faceoff_summary_report, {"faceoffs"}),
        ("toiAway", upd_gms.parse_toi_report, {"powerPlayToi", "shorthandedToi"}),
        ("toiHome", upd_gms.parse_toi_report, {"powerPlayToi", "shorthandedToi"}),
    ],
)
def test_right_rail_html_report_contract(report, parser, fields, live_report_links, live_session):
    url = live_report_links[report]
    assert url, f"Reference game no longer advertises {report}"
    html = upd_gms.fetch_report_html(url, session=live_session)
    assert html, f"Report unavailable: {url}"
    rows = parser(html)
    assert rows, f"No player rows parsed from {report}: {url}"
    assert all(
        isinstance(sweater, int) and fields <= stats.keys() for sweater, stats in rows.items()
    )


def test_event_summary_report_is_available(live_report_links, live_session):
    # Player PP/SH points come from play-by-play, not this HTML report's columns.
    url = live_report_links["eventSummary"]
    assert url, "Reference game no longer advertises Event Summary"
    html = upd_gms.fetch_report_html(url, session=live_session)
    assert html, f"Report unavailable: {url}"
    assert "event summary" in html.lower()
    assert upd_gms.parse_html_tables_rows(html), f"No report tables at {url}"
