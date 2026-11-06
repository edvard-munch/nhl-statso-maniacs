"""Malformed supplied rosters must never replace valid game/player records."""

from copy import deepcopy

from django.core.management.base import CommandError
import pytest

from players.management.commands import upd_gms
from players.models import Game, Gameday, Goalie, Side, Skater, Team
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game, load  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def snapshot(fixture):
    result = {
        model: list(model.objects.order_by("pk").values())
        for model in (Game, Gameday, Side, Skater, Goalie, Team)
    }
    result["rosters"] = {
        game.pk: {
            field: list(getattr(game, field).order_by("pk").values_list("pk", flat=True))
            for field in (
                "away_forwards",
                "away_defencemen",
                "away_goalies",
                "home_forwards",
                "home_defencemen",
                "home_goalies",
            )
        }
        for game in Game.objects.all()
    }
    result["favorites"] = list(fixture.user.favorite_skaters.values_list("pk", flat=True))
    result["comparison"] = list(fixture.user.comparable_skaters.values_list("pk", flat=True))
    return result


def corrupt(payload, defect):
    roster = payload["playerByGameStats"]
    home = roster["homeTeam"]
    row = home["forwards"][0]
    if defect == "root-list":
        payload["playerByGameStats"] = []
    elif defect == "root-string":
        payload["playerByGameStats"] = "invalid"
    elif defect == "side-missing":
        del roster["homeTeam"]
    elif defect == "side-list":
        roster["homeTeam"] = []
    elif defect == "group-missing":
        del home["defense"]
    elif defect == "group-null":
        home["defense"] = None
    elif defect == "group-mapping":
        home["defense"] = {"player": row}
    elif defect == "extra-group":
        home["unknown"] = [row]
    elif defect == "row-null":
        home["defense"] = [None]
    elif defect == "row-list":
        home["defense"] = [[row]]
    elif defect == "id-missing":
        del row["playerId"]
    elif defect == "id-invalid":
        row["playerId"] = True
    elif defect == "position-missing":
        del row["position"]
    elif defect == "wrong-position":
        row["position"] = "G"
    elif defect == "duplicate-same":
        home["forwards"].append(deepcopy(row))
    elif defect == "duplicate-cross-side":
        row["playerId"] = str(roster["awayTeam"]["forwards"][0]["playerId"])
    elif defect == "goalie-toi-missing":
        del home["goalies"][0]["toi"]
    elif defect == "goalie-toi-null":
        home["goalies"][0]["toi"] = None
    elif defect == "goalie-goals-missing":
        del home["goalies"][0]["goalsAgainst"]
    elif defect == "empty-team":
        roster["homeTeam"] = {key: [] for key in home}
    else:
        raise AssertionError(defect)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "defect",
    [
        "root-list",
        "root-string",
        "side-missing",
        "side-list",
        "group-missing",
        "group-null",
        "group-mapping",
        "extra-group",
        "row-null",
        "row-list",
        "id-missing",
        "id-invalid",
        "position-missing",
        "wrong-position",
        "duplicate-same",
        "duplicate-cross-side",
        "goalie-toi-missing",
        "goalie-toi-null",
        "goalie-goals-missing",
        "empty-team",
    ],
)
def test_malformed_roster_preserves_day_and_player_state(loaded_game, existing, defect):
    fixture = loaded_game
    if existing:
        load(fixture)
    before = snapshot(fixture)
    corrupt(fixture.payload, defect)
    with pytest.raises(CommandError) as caught:
        load(fixture)
    error = str(caught.value)
    assert "Gameday " + fixture.day["date"] in error
    assert str(fixture.payload["id"]) in error
    assert upd_gms.URL_BOXSCORE.format(fixture.payload["id"]) in error
    assert "roster" in error.lower()
    assert snapshot(fixture) == before


def test_later_malformed_roster_rolls_back_earlier_game_and_allows_replay(
    loaded_game, requests_mock
):
    fixture = loaded_game
    first = load(fixture)
    second = deepcopy(fixture.payload)
    second["id"] += 1
    for side, nhl_id, abbr in [("awayTeam", 16, "COL"), ("homeTeam", 52, "WPG")]:
        team = Team.objects.create(nhl_id=nhl_id, abbr=abbr, name="Second " + abbr)
        second[side]["id"] = team.nhl_id
        for players in second["playerByGameStats"][side].values():
            for data in players:
                data["playerId"] += 100
                model = Goalie if data["position"] == "G" else Skater
                model.objects.create(
                    nhl_id=data["playerId"],
                    name="Second " + str(data["playerId"]),
                    birth_date="2000-01-01",
                    games=0,
                    gamelog_stats={},
                    team=team,
                )
    valid_second = deepcopy(second)
    before = snapshot(fixture)
    fixture.payload["playerByGameStats"]["awayTeam"]["forwards"][0]["goals"] = 8
    fixture.day["games"].append({"id": second["id"]})
    fixture.register()
    corrupt(second, "group-missing")
    requests_mock.get(upd_gms.URL_BOXSCORE.format(second["id"]), json=second)
    with pytest.raises(CommandError, match=str(second["id"])):
        upd_gms.process_games(fixture.day, None)
    assert snapshot(fixture) == before
    # Repair the failed response and replay the same two-game day twice.
    second = valid_second
    requests_mock.get(upd_gms.URL_BOXSCORE.format(second["id"]), json=second)
    requests_mock.get(upd_gms.URL_RIGHT_RAIL.format(second["id"]), json={})
    requests_mock.get(upd_gms.URL_PLAY_BY_PLAY.format(second["id"]), json={})
    identities = None
    for _ in range(2):
        assert load(fixture).pk == first.pk
        player = fixture.players["away_forward"]
        player.refresh_from_db()
        assert player.gamelog_stats[fixture.day["date"]]["goals"] == 8
        assert player.gamelog_stats["2025-10-01"] == {"historical": True}
        assert Game.objects.count() == 2
        assert Gameday.objects.count() == 1
        assert Side.objects.count() == 4
        assert Gameday.objects.get().all_games_finished
        current = list(Game.objects.order_by("nhl_id").values_list("pk", flat=True))
        if identities is not None:
            assert current == identities
        identities = current
        after = snapshot(fixture)
        assert after["favorites"] == before["favorites"]
        assert after["comparison"] == before["comparison"]


@pytest.mark.parametrize("missing", [None, {}])
def test_unavailable_roster_stays_pending_without_erasing_previous_players(loaded_game, missing):
    fixture = loaded_game
    load(fixture)
    before = snapshot(fixture)
    fixture.payload["playerByGameStats"] = missing
    game = load(fixture)
    assert not game.game_finished
    assert not game.gameday.all_games_finished
    assert game.gameday.all_games_uploaded
    after = snapshot(fixture)
    for key in (Skater, Goalie, "rosters", "favorites", "comparison"):
        assert after[key] == before[key]


def test_nested_legacy_roster_remains_supported(loaded_game):
    fixture = loaded_game
    fixture.payload["boxscore"] = {"playerByGameStats": fixture.payload.pop("playerByGameStats")}
    assert load(fixture).game_finished
    assert Game.objects.get().home_forwards.count() == 1
