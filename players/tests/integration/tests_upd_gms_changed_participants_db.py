"""Corrected game rosters must not leave verified stale gamelog appearances."""

from copy import deepcopy

from django.core.management.base import CommandError
import pytest

from players.management.commands import upd_gms
from players.models import Game, Gameday, Goalie, Skater
from players.tests.integration.tests_upd_gms_malformed_rosters_db import snapshot
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game, load  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def roster(fixture, key):
    side, kind = key.split("_")
    group = {"forward": "forwards", "defense": "defense", "goalie": "goalies"}[kind]
    relation = side + "_" + ("defencemen" if kind == "defense" else group)
    return fixture.payload["playerByGameStats"][side + "Team"][group], relation


def remove(fixture, key):
    rows, relation = roster(fixture, key)
    old = fixture.players[key]
    data = next(row for row in rows if row["playerId"] == old.nhl_id)
    rows.remove(data)
    return old, data, relation


@pytest.mark.parametrize(
    "key",
    ["away_forward", "away_defense", "away_goalie", "home_forward", "home_defense", "home_goalie"],
)
@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_removed_or_replaced_participants_lose_only_this_games_log(
    loaded_game, key, replacement, legacy
):
    fixture = loaded_game
    old = fixture.players[key]
    old.favoriting.add(fixture.user)
    old.comparing.add(fixture.user)
    original = load(fixture)
    old.refresh_from_db()
    if legacy:
        old.gamelog_stats[fixture.day["date"]].pop("gameId", None)
        old.save(update_fields=["gamelog_stats"])
    before = type(old).objects.values().get(pk=old.pk)
    before_all = {model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie)}
    old, data, relation = remove(fixture, key)
    new = None
    if replacement:
        new = type(old).objects.create(
            nhl_id=900100,
            name="Replacement Player",
            birth_date="2000-01-01",
            games=0,
            gamelog_stats={"2024-10-01": {"older": True}},
        )
        rows, _ = roster(fixture, key)
        rows.append(dict(data, playerId=new.nhl_id))
    for _ in range(2):
        game = load(fixture)
        assert game.pk == original.pk and game.slug == original.slug
        assert game.game_finished and game.gameday.all_games_finished
        assert not getattr(game, relation).filter(pk=old.pk).exists()
        expected = deepcopy(before)
        del expected["gamelog_stats"][fixture.day["date"]]
        assert type(old).objects.values().get(pk=old.pk) == expected
        assert old.favoriting.filter(pk=fixture.user.pk).exists()
        assert old.comparing.filter(pk=fixture.user.pk).exists()
        for model, records in before_all.items():
            for record in records:
                if model is type(old) and record["id"] == old.pk:
                    continue
                assert model.objects.values().get(pk=record["id"]) == record
        if new is not None:
            new.refresh_from_db()
            assert getattr(game, relation).filter(pk=new.pk).exists()
            assert new.gamelog_stats[fixture.day["date"]]["gameId"] == game.nhl_id
            assert new.gamelog_stats["2024-10-01"] == {"older": True}
        assert Game.objects.count() == Gameday.objects.count() == 1


@pytest.mark.parametrize("side", ["away", "home"])
def test_goalie_corrected_to_bench_loses_appearance_but_replacement_keeps_it(loaded_game, side):
    fixture = loaded_game
    load(fixture)
    fixture.payload["playerByGameStats"][side + "Team"]["goalies"][0]["toi"] = "00:00"
    fixture.payload["playerByGameStats"][side + "Team"]["goalies"][1]["toi"] = "60:00"
    game = load(fixture)
    old, new = fixture.players[side + "_goalie"], fixture.players[side + "_bench"]
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.gamelog_stats == {"2025-10-01": {"historical": True}}
    assert list(getattr(game, side + "_goalies").all()) == [new]
    assert new.gamelog_stats[fixture.day["date"]]["gameId"] == game.nhl_id
    assert new.gamelog_stats[fixture.day["date"]]["shutout"] == 1


@pytest.mark.parametrize("change", ["position", "side"])
def test_retained_player_moving_group_or_side_keeps_updated_appearance(loaded_game, change):
    fixture = loaded_game
    load(fixture)
    old, data, relation = remove(fixture, "away_forward")
    if change == "position":
        data["position"] = "D"
        fixture.payload["playerByGameStats"]["awayTeam"]["defense"].append(data)
        destination, team = "away_defencemen", fixture.away
    else:
        fixture.payload["playerByGameStats"]["homeTeam"]["forwards"].append(data)
        destination, team = "home_forwards", fixture.home
    game = load(fixture)
    old.refresh_from_db()
    assert not getattr(game, relation).filter(pk=old.pk).exists()
    assert getattr(game, destination).filter(pk=old.pk).exists()
    assert old.gamelog_stats[fixture.day["date"]]["team"]["abbr"] == team.abbr
    assert old.gamelog_stats[fixture.day["date"]]["gameId"] == game.nhl_id
    assert old.gamelog_stats["2025-10-01"] == {"historical": True}


@pytest.mark.parametrize(
    "conflict",
    [
        "other-game-id",
        "other-teams",
        "same-date-game",
        "wrong-player",
        "invalid-game-id",
        "malformed-metadata",
        "unstructured-entry",
    ],
)
def test_unverified_or_other_game_entries_are_retained_with_warning(loaded_game, conflict, caplog):
    fixture = loaded_game
    game = load(fixture)
    player = fixture.players["away_forward"]
    player.refresh_from_db()
    entry = player.gamelog_stats[fixture.day["date"]]
    if conflict == "other-game-id":
        entry["gameId"] = game.nhl_id + 1
    elif conflict == "wrong-player":
        entry["player"]["nhl_id"] += 1
    elif conflict == "invalid-game-id":
        entry["gameId"] = None
    elif conflict == "unstructured-entry":
        player.gamelog_stats[fixture.day["date"]] = "Unverified legacy data"
    else:
        entry.pop("gameId", None)
        if conflict == "other-teams":
            entry["team"]["abbr"] = "COL"
        elif conflict == "malformed-metadata":
            entry["team"]["abbr"] = ["NJD"]
        else:
            other = Game.objects.create(nhl_id=game.nhl_id + 1, gameday=game.gameday)
            other.home_forwards.add(player)
    player.save(update_fields=["gamelog_stats"])
    before = deepcopy(player.gamelog_stats)
    remove(fixture, "away_forward")
    game = load(fixture)
    player.refresh_from_db()
    assert not game.away_forwards.filter(pk=player.pk).exists()
    assert player.gamelog_stats == before
    assert "unverified gamelog" in caplog.text


def test_removal_does_not_confuse_skater_and_goalie_with_same_database_pk(loaded_game):
    fixture = loaded_game
    pk = (
        max(Skater.objects.order_by("-pk").first().pk, Goalie.objects.order_by("-pk").first().pk)
        + 1
    )
    for key, model, nhl_id in [("away_forward", Skater, 900101), ("away_goalie", Goalie, 900102)]:
        old = fixture.players[key]
        rows, _ = roster(fixture, key)
        data = next(row for row in rows if row["playerId"] == old.nhl_id)
        data["playerId"] = nhl_id
        fixture.players[key] = model.objects.create(
            pk=pk,
            nhl_id=nhl_id,
            name="Typed " + key,
            birth_date="2000-01-01",
            games=0,
            gamelog_stats={},
        )
    load(fixture)
    goalie = fixture.players["away_goalie"]
    before = Goalie.objects.values().get(pk=goalie.pk)
    old, _, _ = remove(fixture, "away_forward")
    game = load(fixture)
    assert not game.away_forwards.exists()
    old.refresh_from_db()
    assert fixture.day["date"] not in old.gamelog_stats
    assert list(game.away_goalies.all()) == [goalie]
    assert Goalie.objects.values().get(pk=goalie.pk) == before


def test_later_failure_restores_removed_logs_and_links_then_allows_retry(
    loaded_game, requests_mock
):
    fixture = loaded_game
    load(fixture)
    before = snapshot(fixture)
    remove(fixture, "away_forward")
    fixture.day["games"].append({"id": 2026020002})
    invalid = deepcopy(fixture.payload)
    invalid["id"] = 2026020002
    invalid["playerByGameStats"]["homeTeam"]["defense"] = None
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020002), json=invalid)
    with pytest.raises(CommandError, match="2026020002"):
        load(fixture)
    assert snapshot(fixture) == before
    fixture.day["games"].pop()
    game = load(fixture)
    old = fixture.players["away_forward"]
    old.refresh_from_db()
    assert fixture.day["date"] not in old.gamelog_stats
    assert not game.away_forwards.filter(pk=old.pk).exists()


def test_missing_replacement_keeps_game_pending_without_retaining_removed_player(loaded_game):
    fixture = loaded_game
    load(fixture)
    old, data, _ = remove(fixture, "away_forward")
    fixture.payload["playerByGameStats"]["awayTeam"]["forwards"].append(dict(data, playerId=999999))
    game = load(fixture)
    old.refresh_from_db()
    assert not game.game_finished and not game.gameday.all_games_finished
    assert not game.away_forwards.exists()
    assert fixture.day["date"] not in old.gamelog_stats
