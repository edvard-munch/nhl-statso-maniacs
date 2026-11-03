"""Resolve HTML jerseys to roster identities before enriching individual players."""

import pytest

from players.management.commands import upd_gms


pytestmark = pytest.mark.unit


@pytest.fixture
def rosters():
    return {
        "playerByGameStats": {
            "awayTeam": {
                "forwards": [{"playerId": "100", "sweaterNumber": "98"}],
                "goalies": [{"playerId": 101, "sweaterNumber": 98, "toi": "00:00"}],
            },
            "homeTeam": {"forwards": [{"playerId": 200, "sweaterNumber": 98}]},
        }
    }


def test_team_scope_resolves_shared_jerseys_and_excludes_unused_goalies(rosters):
    assert upd_gms.map_report_sweaters_to_players(rosters) == {98: {100, 200}}
    away = upd_gms.map_report_sweaters_to_players(rosters, "awayTeam")
    home = upd_gms.map_report_sweaters_to_players(rosters, "homeTeam")
    assert upd_gms.resolve_report_players({98: {"powerPlayToi": "02:10"}}, away, "away") == {
        100: {"powerPlayToi": "02:10"}
    }
    assert upd_gms.resolve_report_players({98: {"powerPlayToi": "00:25"}}, home, "home") == {
        200: {"powerPlayToi": "00:25"}
    }


def test_unscoped_html_assigns_only_unique_roster_identities(caplog):
    stats = {98: {"faceoffs": 12}, 16: {"faceoffs": 4}, 99: {"faceoffs": 9}}
    roster = {98: {100, 200}, 16: {300}}
    assert upd_gms.resolve_report_players(stats, roster, "faceoffs") == {300: {"faceoffs": 4}}
    assert "ambiguous sweater 98" in caplog.text


def test_legacy_nested_boxscore_roster_has_the_same_identity_scope(rosters):
    nested = {"boxscore": rosters}
    assert upd_gms.map_report_sweaters_to_players(nested, "awayTeam") == {98: {100}}
    assert upd_gms.map_report_sweaters_to_players(nested) == {98: {100, 200}}


@pytest.mark.parametrize("player_id", [100, "100"])
def test_hydration_uses_player_id_even_when_jersey_matches_another_key(player_id):
    player = {"playerId": player_id, "sweaterNumber": 98, "powerPlayPoints": 0}
    upd_gms.hydrate_player_stats_from_reports(
        player,
        {
            98: {"faceoffs": 99},
            100: {"faceoffs": 4, "powerPlayPoints": 3},
        },
    )
    assert player["faceoffs"] == 4
    assert player["powerPlayPoints"] == 0


def test_missing_player_id_does_not_fall_back_to_sweater_number():
    player = {"sweaterNumber": 98}
    upd_gms.hydrate_player_stats_from_reports(player, {98: {"faceoffs": 99}})
    assert "faceoffs" not in player


def test_play_by_play_keeps_known_player_ids_without_needing_a_sweater():
    points = {
        "100": {"powerPlayPoints": 2, "shPoints": 0},
        200: {"powerPlayPoints": 0, "shPoints": 1},
        999: {"powerPlayPoints": 9, "shPoints": 9},
    }
    assert upd_gms.filter_special_teams_points(points, {100, 200}) == {
        100: {"powerPlayPoints": 2, "shPoints": 0},
        200: {"powerPlayPoints": 0, "shPoints": 1},
    }
