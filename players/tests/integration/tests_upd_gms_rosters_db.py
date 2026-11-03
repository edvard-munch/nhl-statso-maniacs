"""Mocked NHL inputs through real game, roster and gamelog persistence."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.core.management.base import CommandError
import requests

from players.management.commands import upd_gms
from players.models import Game, Gameday, Goalie, Side, Skater, Team


pytestmark = [pytest.mark.integration, pytest.mark.django_db]
REPORT_FIXTURES = Path(__file__).parents[1] / "unit/other/files"


@pytest.fixture
def loaded_game(monkeypatch, requests_mock):
    monkeypatch.setattr(upd_gms, "sleep", lambda delay: None)
    away = Team.objects.create(nhl_id=1, abbr="NJD", name="Fixture Away")
    home = Team.objects.create(nhl_id=7, abbr="BUF", name="Fixture Home")
    specs = [
        ("away_forward", Skater, 900001, "C", 98),
        ("away_defense", Skater, 900002, "D", 16),
        ("away_goalie", Goalie, 900003, "G", 31),
        ("away_bench", Goalie, 900004, "G", 30),
        ("home_forward", Skater, 900005, "LW", 13),
        ("home_defense", Skater, 900006, "D", 59),
        ("home_goalie", Goalie, 900007, "G", 35),
        ("home_bench", Goalie, 900008, "G", 40),
    ]
    players = {}
    rosters = {
        side: {"forwards": [], "defense": [], "goalies": []} for side in ("awayTeam", "homeTeam")
    }
    for key, model, nhl_id, position, sweater in specs:
        player = model.objects.create(
            nhl_id=nhl_id,
            name="Fixture " + key,
            birth_date="2000-01-01",
            games=99,
            position_abbr=position,
            team=home,
            sbs_stats=[{"season": "2025-26", "goals": 8}],
            career_stats={"gamesPlayed": 99},
            gamelog_stats={"2025-10-01": {"historical": True}},
        )
        players[key] = player
        data = {
            "playerId": nhl_id,
            "name": {"default": player.name},
            "position": position,
            "sweaterNumber": sweater,
            "toi": "00:00" if key.endswith("bench") else "20:00",
            "goals": 1,
            "assists": 2,
            "points": 3,
            "goalsAgainst": 0,
        }
        group = "goalies" if position == "G" else "defense" if position == "D" else "forwards"
        rosters["awayTeam" if key.startswith("away") else "homeTeam"][group].append(data)
    # Explicit zero and nonzero boxscore values take precedence over reports.
    rosters["awayTeam"]["defense"][0].update(
        faceoffs=0, powerPlayPoints=3, shPoints=0, powerPlayToi="02:00"
    )
    payload = {
        "id": 2026020001,
        "gameState": "OFF",
        "awayTeam": {"id": away.nhl_id, "score": 1},
        "homeTeam": {"id": home.nhl_id, "score": 0},
        "periodDescriptor": {"number": 3},
        "playerByGameStats": rosters,
    }
    day = {"date": "2026-11-21", "games": [{"id": payload["id"]}]}
    reports = {}
    for key, filename in [
        ("eventSummary", "report_event_summary.html"),
        ("faceoffSummary", "report_faceoff_summary.html"),
        ("toiAway", "report_toi.html"),
        ("toiHome", "report_toi.html"),
    ]:
        url = "https://reports.invalid/" + key
        reports[key] = url
        requests_mock.get(url, text=(REPORT_FIXTURES / filename).read_text())
    requests_mock.get(upd_gms.URL_RIGHT_RAIL.format(payload["id"]), json={"gameReports": reports})
    play_by_play = {
        "awayTeam": {"id": away.nhl_id},
        "homeTeam": {"id": home.nhl_id},
        "plays": [
            {
                "typeDescKey": "goal",
                "situationCode": "1541",
                "details": {
                    "eventOwnerTeamId": away.nhl_id,
                    "scoringPlayerId": players["away_forward"].nhl_id,
                },
            },
            {
                "typeDescKey": "goal",
                "situationCode": "1541",
                "details": {
                    "eventOwnerTeamId": home.nhl_id,
                    "scoringPlayerId": players["home_defense"].nhl_id,
                },
            },
        ],
    }
    requests_mock.get(upd_gms.URL_PLAY_BY_PLAY.format(payload["id"]), json=play_by_play)
    user = User.objects.create_user(username="game-contract-user")
    user.favorite_skaters.add(players["away_forward"])
    user.comparable_skaters.add(players["away_forward"])

    def register():
        requests_mock.get(upd_gms.URL_BOXSCORE.format(payload["id"]), json=payload)

    register()
    return SimpleNamespace(
        players=players,
        payload=payload,
        day=day,
        away=away,
        home=home,
        user=user,
        register=register,
    )


def load(fixture):
    fixture.register()
    with requests.Session() as session:
        upd_gms.process_games(fixture.day, session)
    return Game.objects.get(nhl_id=fixture.payload["id"])


def log_for(fixture, key):
    player = fixture.players[key]
    player.refresh_from_db()
    return player.gamelog_stats[fixture.day["date"]]


def test_finished_game_persists_all_roster_groups_and_enriched_gamelogs(loaded_game):
    fixture = loaded_game
    game = load(fixture)
    assert game.result == "Fixture Away - Fixture Home 1:0"
    for relation, key in [
        ("away_forwards", "away_forward"),
        ("away_defencemen", "away_defense"),
        ("away_goalies", "away_goalie"),
        ("home_forwards", "home_forward"),
        ("home_defencemen", "home_defense"),
        ("home_goalies", "home_goalie"),
    ]:
        assert list(getattr(game, relation).all()) == [fixture.players[key]]
    assert {(side.side, side.team_id) for side in game.side_set.all()} == {
        ("away", fixture.away.pk),
        ("home", fixture.home.pk),
    }
    forward = log_for(fixture, "away_forward")
    assert (forward["goals"], forward["assists"], forward["faceoffs"]) == (1, 2, 12)
    assert (forward["powerPlayPoints"], forward["shPoints"]) == (1, 0)
    assert (forward["powerPlayToi"], forward["shorthandedToi"]) == ("04:31", "01:05")
    assert forward["team"] == {"name": fixture.away.name, "abbr": fixture.away.abbr}
    assert forward["opponent"] == {"name": fixture.home.name, "abbr": fixture.home.abbr}
    assert forward["player"]["nhl_id"] == fixture.players["away_forward"].nhl_id
    assert forward["format_date"] == "Nov 21"
    defense = log_for(fixture, "away_defense")
    assert (defense["faceoffs"], defense["powerPlayPoints"], defense["powerPlayToi"]) == (
        0,
        3,
        "02:00",
    )
    assert defense["shorthandedToi"] == "0:44"
    assert log_for(fixture, "home_defense")["shPoints"] == 1
    assert log_for(fixture, "home_forward")["faceoffs"] == 0
    assert log_for(fixture, "home_forward")["powerPlayToi"] == "00:00"
    assert log_for(fixture, "away_goalie")["shutout"] == 1
    assert game.game_finished is True
    assert game.gameday.all_games_finished is game.gameday.all_games_uploaded is True


def test_repeat_load_updates_same_date_and_preserves_history_and_saved_lists(loaded_game):
    fixture = loaded_game
    first = load(fixture)
    fixture.payload["playerByGameStats"]["awayTeam"]["forwards"][0]["goals"] = 4
    second = load(fixture)
    assert first.pk == second.pk
    assert Game.objects.count() == Gameday.objects.count() == 1
    assert Side.objects.count() == 2
    player = fixture.players["away_forward"]
    assert log_for(fixture, "away_forward")["goals"] == 4
    assert set(player.gamelog_stats) == {"2025-10-01", "2026-11-21"}
    assert player.gamelog_stats["2025-10-01"] == {"historical": True}
    assert player.games == 99 and player.team_id == fixture.home.pk
    assert player.sbs_stats == [{"season": "2025-26", "goals": 8}]
    assert player.career_stats == {"gamesPlayed": 99}
    assert list(player.favoriting.all()) == list(player.comparing.all()) == [fixture.user]


@pytest.mark.parametrize(
    "state, finished",
    [
        ("FUT", False),
        ("PRE", False),
        ("LIVE", False),
        ("CRIT", False),
        ("OVER", False),
        ("FINAL", True),
        ("OFF", True),
    ],
)
def test_only_final_game_states_mark_games_and_days_finished(loaded_game, state, finished):
    loaded_game.payload["gameState"] = state
    game = load(loaded_game)
    assert game.game_finished is finished
    assert game.gameday.all_games_finished is finished
    assert game.gameday.all_games_uploaded is True


def test_missing_player_keeps_day_pending_until_player_is_loaded(loaded_game, caplog):
    fixture = loaded_game
    assert load(fixture).gameday.all_games_finished is True
    missing = fixture.players["home_defense"]
    identity = {
        "nhl_id": missing.nhl_id,
        "name": missing.name,
        "birth_date": missing.birth_date,
        "games": 0,
        "position_abbr": "D",
    }
    missing.delete()
    game = load(fixture)
    assert game.game_finished is game.gameday.all_games_finished is False
    assert game.gameday.all_games_uploaded is True
    assert not game.home_defencemen.exists()
    assert "not found" in caplog.text
    fixture.players["home_defense"] = Skater.objects.create(**identity)
    game = load(fixture)
    assert game.game_finished is game.gameday.all_games_finished is True
    assert log_for(fixture, "home_defense")["shPoints"] == 1


def test_bench_goalies_are_excluded_and_shared_shutout_is_not_awarded(loaded_game):
    fixture = loaded_game
    first = load(fixture)
    for key in ("away_bench", "home_bench"):
        fixture.players[key].refresh_from_db()
        assert fixture.day["date"] not in fixture.players[key].gamelog_stats
    assert first.away_goalies.count() == first.home_goalies.count() == 1
    fixture.payload["playerByGameStats"]["awayTeam"]["goalies"][1]["toi"] = "10:00"
    game = load(fixture)
    assert game.away_goalies.count() == 2
    assert log_for(fixture, "away_goalie")["shutout"] == 0
    assert log_for(fixture, "away_bench")["shutout"] == 0


def test_missing_roster_on_refresh_clears_completion_flags(loaded_game):
    fixture = loaded_game
    assert load(fixture).gameday.all_games_finished is True
    fixture.payload.pop("playerByGameStats")
    game = load(fixture)
    assert game.game_finished is False
    assert game.gameday.all_games_finished is False
    assert game.gameday.all_games_uploaded is True


def test_later_failure_rolls_back_actual_player_gamelogs_and_relations(loaded_game, requests_mock):
    fixture = loaded_game
    before = {key: deepcopy(player.gamelog_stats) for key, player in fixture.players.items()}
    fixture.day["games"].append({"id": 2026020002})
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020002), text="<html>Unavailable</html>")
    with pytest.raises(CommandError, match="2026020002"):
        load(fixture)
    assert Game.objects.count() == Gameday.objects.count() == Side.objects.count() == 0
    for key, player in fixture.players.items():
        player.refresh_from_db()
        assert player.gamelog_stats == before[key]
    assert fixture.user.favorite_skaters.count() == fixture.user.comparable_skaters.count() == 1


@pytest.mark.parametrize("initial_state", ["OFF", "LIVE"])
@pytest.mark.parametrize("existing_pending_day", [False, True])
def test_command_loads_and_replays_schedule_without_duplicate_records(
    loaded_game, monkeypatch, requests_mock, initial_state, existing_pending_day
):
    fixture = loaded_game

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 21, 12, tzinfo=tz)

    monkeypatch.setattr(upd_gms, "datetime", FrozenDateTime)
    requests_mock.get(
        upd_gms.URL_SCHEDULE.format("2026-11-21"),
        json={
            "regularSeasonStartDate": "2026-11-21",
            "regularSeasonEndDate": "2026-11-21",
            "gameWeek": [fixture.day],
        },
    )
    if existing_pending_day:
        Gameday.objects.create(day=fixture.day["date"])
    for attempt in range(2):
        fixture.payload["gameState"] = initial_state if attempt == 0 else "OFF"
        fixture.register()
        upd_gms.Command().handle()
        assert Game.objects.get().game_finished is (attempt > 0 or initial_state == "OFF")
        assert Gameday.objects.get().all_games_finished is (attempt > 0 or initial_state == "OFF")
        assert Game.objects.count() == Gameday.objects.count() == 1
        assert Side.objects.count() == 2
        assert log_for(fixture, "away_forward")["goals"] == 1


def test_one_scheduled_game_keeps_an_otherwise_finished_day_pending(loaded_game, requests_mock):
    fixture = loaded_game
    away = Team.objects.create(nhl_id=16, abbr="COL", name="Other Away")
    home = Team.objects.create(nhl_id=52, abbr="WPG", name="Other Home")
    fixture.day["games"].append({"id": 2026020002})
    requests_mock.get(
        upd_gms.URL_BOXSCORE.format(2026020002),
        json={
            "gameState": "FUT",
            "awayTeam": {"id": away.nhl_id},
            "homeTeam": {"id": home.nhl_id},
        },
    )
    game = load(fixture)
    assert game.game_finished is True
    assert Game.objects.get(nhl_id=2026020002).game_finished is False
    assert game.gameday.all_games_uploaded is True
    assert game.gameday.all_games_finished is False
    assert Side.objects.count() == 4
