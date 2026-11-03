"""A jersey shared by opponents must not identify one player in a game."""

import pytest

from players.management.commands import upd_gms
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game, load, log_for  # noqa: F401


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("boxscore_values", [False, True])
def test_shared_sweaters_keep_points_and_team_toi_separate(
    loaded_game, requests_mock, boxscore_values, caplog
):
    fixture = loaded_game
    away = fixture.payload["playerByGameStats"]["awayTeam"]["forwards"][0]
    home = fixture.payload["playerByGameStats"]["homeTeam"]["defense"][0]
    home["sweaterNumber"] = away["sweaterNumber"]
    requests_mock.get(
        "https://reports.invalid/toiHome",
        text="""
        <table><tr><th>#</th><th>TOI PP</th><th>TOI SH</th></tr>
        <tr><td>98</td><td>00:22</td><td>02:10</td></tr></table>
    """,
    )
    if boxscore_values:
        away.update(faceoffs=5, powerPlayPoints=4, powerPlayToi="03:00")
        home.update(faceoffs=7, shPoints=2, shorthandedToi="04:00")
    for _ in range(2):
        game = load(fixture)
        assert game.game_finished is True
        away_log = log_for(fixture, "away_forward")
        home_log = log_for(fixture, "home_defense")
        assert (away_log["powerPlayPoints"], away_log["shPoints"]) == (
            4 if boxscore_values else 1,
            0,
        )
        assert (home_log["powerPlayPoints"], home_log["shPoints"]) == (
            0,
            2 if boxscore_values else 1,
        )
        assert (away_log["powerPlayToi"], away_log["shorthandedToi"]) == (
            "03:00" if boxscore_values else "04:31",
            "01:05",
        )
        assert (home_log["powerPlayToi"], home_log["shorthandedToi"]) == (
            "00:22",
            "04:00" if boxscore_values else "02:10",
        )
        # Unscoped HTML cannot resolve the shared jersey; existing defaults apply.
        assert away_log["faceoffs"] == (5 if boxscore_values else 0)
        assert home_log["faceoffs"] == (7 if boxscore_values else 0)
    assert "ambiguous sweater 98" in caplog.text


def test_non_scoring_opponent_does_not_inherit_shared_sweater_points(loaded_game, requests_mock):
    fixture = loaded_game
    fixture.payload["playerByGameStats"]["homeTeam"]["defense"][0]["sweaterNumber"] = 98
    requests_mock.get(
        upd_gms.URL_PLAY_BY_PLAY.format(fixture.payload["id"]),
        json={
            "awayTeam": {"id": fixture.away.nhl_id},
            "homeTeam": {"id": fixture.home.nhl_id},
            "plays": [
                {
                    "typeDescKey": "goal",
                    "situationCode": "1541",
                    "details": {
                        "eventOwnerTeamId": fixture.away.nhl_id,
                        "scoringPlayerId": fixture.players["away_forward"].nhl_id,
                    },
                }
            ],
        },
    )
    load(fixture)
    assert log_for(fixture, "away_forward")["powerPlayPoints"] == 1
    assert log_for(fixture, "home_defense")["powerPlayPoints"] == 0
