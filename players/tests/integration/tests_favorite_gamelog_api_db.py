"""Aggregated favorite game rows retain public verification and private ownership."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
import pytest

from players.models import Game, Gameday, Goalie, Side, Skater
from players.tests.integration.tests_game_pages_db import game_page  # noqa: F401
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game  # noqa: F401
from players.tests.integration.tests_favorites_api_db import concurrent_changes, csrf
from players.tests.integration.tests_saved_player_actions_db import state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock, monkeypatch):
    monkeypatch.setattr(
        "players.api.player_logs.timezone.now", lambda: datetime(2026, 11, 10, tzinfo=timezone.utc)
    )
    return requests_mock


@pytest.fixture
def saved_games(client, game_page):
    f = game_page
    # The loader fixture also seeds older unrelated dates. Define this slice's
    # log explicitly; history-specific tests add their own dated evidence.
    for player in f.players.values():
        player.refresh_from_db()
        dates = {f.day["date"], "2026-11-20"} if isinstance(player, Skater) else {f.day["date"]}
        player.gamelog_stats = {
            key: row for key, row in player.gamelog_stats.items() if key in dates
        }
        player.save(update_fields=["gamelog_stats"])
    f.owner = get_user_model().objects.create_user(username="favorite-games-owner")
    f.other = get_user_model().objects.create_user(username="favorite-games-other")
    f.owner.favorite_skaters.add(f.players["away_forward"], f.players["home_defense"])
    f.owner.favorite_goalies.add(f.players["away_goalie"])
    f.other.favorite_skaters.add(f.players["home_forward"])
    f.owner.comparable_skaters.add(f.players["home_forward"])
    client.force_login(f.owner)
    return f


def listing(client, **params):
    return client.get(reverse("api_v1:favorites-gamelog"), params)


def linked(data):
    return [row for row in data["results"] if row["game"]]


def test_saved_rows_equal_public_gamelogs_and_game_detail_with_explicit_identity(
    client, saved_games
):
    f = saved_games
    response = listing(client)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 4 and len(linked(data)) == 2
    assert {row["player"]["nhl_id"] for row in data["results"]} == {
        f.players[key].nhl_id for key in ("away_forward", "home_defense")
    }
    for row in linked(data):
        identity = row["player"]
        public = client.get(
            reverse("api_v1:player-gamelog", args=["skater", identity["nhl_id"]])
        ).json()
        public_row = next(
            entry for entry in linked(public) if entry["game"]["nhl_id"] == row["game"]["nhl_id"]
        )
        assert {key: value for key, value in row.items() if key != "player"} == public_row
        assert row["stats"]["pp_toi_seconds"] in (61, 64)
        assert row["stats"]["sh_toi_seconds"] in (121, 124)
    detail = client.get(reverse("api_v1:game-detail", args=[f.game.nhl_id])).json()
    first = next(
        row for row in linked(data) if row["player"]["nhl_id"] == f.players["away_forward"].nhl_id
    )
    assert first["game"]["state"] == detail["state"]
    assert first["stats"] == detail["rosters"]["away"]["forwards"][0]["stats"]
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
    assert "cookie" in response["Vary"].lower() and response["X-Request-ID"]
    assert data["meta"]["season_id"] is None and data["meta"]["ordering"] == "-date"
    assert data["meta"]["quota"]["total_count"] == 3


def test_goalies_are_typed_and_keep_fraction_units(client, saved_games):
    data = listing(client, player_type="goalie").json()
    assert data["count"] == 1
    row = data["results"][0]
    assert row["player"]["player_type"] == "goalie"
    assert row["player"]["nhl_id"] == saved_games.players["away_goalie"].nhl_id
    assert row["stats"]["save_percentage"] == 0.923 and row["stats"]["toi_seconds"] == 3600
    assert row["stats"]["saves"] == 24 and row["stats"]["shots_against"] == 26
    assert (
        listing(client, player_type="goalie", ordering="decision", saves_min=24).json()["count"]
        == 1
    )
    assert listing(client, player_type="goalie", save_percentage_min=0.95).json()["count"] == 0


def test_season_date_team_statistic_and_literal_search_filters_precede_pagination(
    client, saved_games
):
    f = saved_games
    day = f.day["date"]
    data = listing(client, goals_min=2, page_size=1).json()
    assert data["count"] == 1 and data["results"][0]["stats"]["goals"] == 4
    assert data["meta"]["quota"]["total_count"] == 3
    assert listing(client, season_id="20262027").json()["count"] == 2
    assert listing(client, season_id="20252026").json()["count"] == 0
    assert listing(client, date_min=day, date_max=day).json()["count"] == 2
    for team_field, abbr in [("team", f.away.abbr), ("opponent", f.home.abbr)]:
        rows = listing(client, **{team_field: abbr}).json()["results"]
        assert len(rows) == 1 and rows[0]["player"]["nhl_id"] == f.players["away_forward"].nhl_id
    search = f.players["away_forward"].name.swapcase()
    data = listing(client, search=search, page_size=1).json()
    assert data["count"] == 2 and data["next"]
    assert client.get(data["next"]).json()["meta"] == data["meta"]
    for literal in ("%", "' OR 1=1 --"):
        assert listing(client, search=literal).json()["count"] == 0
    assert listing(client, goals_isnull="true").json()["count"] == 2
    assert listing(client, goals_isnull="false").json()["count"] == 2
    for ordering in ("goals", "-goals"):
        rows = listing(client, ordering=ordering).json()["results"]
        assert rows[-1]["stats"]["goals"] is None


def test_all_history_has_no_legacy_200_row_cap_and_pages_are_global(client, saved_games):
    player = saved_games.players["away_forward"]
    player.refresh_from_db()
    prototype = deepcopy(player.gamelog_stats[saved_games.day["date"]])
    for index in range(205):
        player.gamelog_stats[(date(2020, 1, 1) + timedelta(days=index)).isoformat()] = prototype
    player.save(update_fields=["gamelog_stats"])
    data = listing(client, page_size=100).json()
    assert data["count"] == 209 and len(data["results"]) == 100
    second = client.get(data["next"]).json()
    third = client.get(second["next"]).json()
    assert len(second["results"]) == 100 and len(third["results"]) == 9
    keys = [
        (row["player"]["nhl_id"], row["date"])
        for page in (data, second, third)
        for row in page["results"]
    ]
    assert len(set(keys)) == 209
    assert listing(client, page_size=100, page=4).status_code == 404


@pytest.mark.parametrize(
    "damage,availability",
    [
        ("player", "unverified"),
        ("game", "unverified"),
        ("position", "unverified"),
        ("missing", "missing"),
        ("times", "partial"),
    ],
)
def test_bad_saved_rows_keep_identity_without_guessing_statistics(
    client, saved_games, damage, availability
):
    player = saved_games.players["away_forward"]
    player.refresh_from_db()
    raw = player.gamelog_stats[saved_games.day["date"]]
    if damage == "player":
        raw["player"]["nhl_id"] = 999999
    elif damage == "game":
        raw["gameId"] = 2026029999
    elif damage == "position":
        raw["position"] = "G"
    elif damage == "missing":
        player.gamelog_stats.pop(saved_games.day["date"])
    else:
        raw["powerPlayToi"] = "invalid"
    player.save(update_fields=["gamelog_stats"])
    row = next(
        row for row in linked(listing(client).json()) if row["player"]["nhl_id"] == player.nhl_id
    )
    assert row["availability"] == availability
    if availability in ("missing", "unverified"):
        assert all(value is None for value in row["stats"].values())
    else:
        assert row["stats"]["pp_toi_seconds"] is None and row["stats"]["sh_toi_seconds"] == 121


def test_legacy_collisions_are_per_player_and_stamped_games_remain_distinct(client, saved_games):
    f = saved_games
    player = f.players["away_forward"]
    player.refresh_from_db()
    player.gamelog_stats[f.day["date"]].pop("gameId", None)
    player.save(update_fields=["gamelog_stats"])
    # Two favorites in one game/date are not a legacy identity collision.
    assert all(
        row["availability"] in ("complete", "partial") for row in linked(listing(client).json())
    )
    other = Game.objects.create(nhl_id=2026029998, gameday=f.game.gameday)
    other.away_forwards.add(player)
    rows = linked(listing(client).json())
    assert len(rows) == 3
    assert all(
        row["availability"] == "unverified"
        for row in rows
        if row["player"]["nhl_id"] == player.nhl_id
    )
    assert next(row for row in rows if row["player"]["nhl_id"] != player.nhl_id)[
        "availability"
    ] in ("complete", "partial")
    player.gamelog_stats[f.day["date"]]["gameId"] = f.game.nhl_id
    player.save(update_fields=["gamelog_stats"])
    rows = [
        row for row in linked(listing(client).json()) if row["player"]["nhl_id"] == player.nhl_id
    ]
    assert (
        next(row for row in rows if row["game"]["nhl_id"] == f.game.nhl_id)["stats"]["goals"] == 1
    )
    assert (
        next(row for row in rows if row["game"]["nhl_id"] == other.nhl_id)["availability"]
        == "unverified"
    )


def test_duplicate_roster_and_undated_games_stay_explicit(client, saved_games):
    f = saved_games
    player = f.players["away_forward"]
    f.game.away_defencemen.add(player)
    row = next(
        row for row in linked(listing(client).json()) if row["player"]["nhl_id"] == player.nhl_id
    )
    assert row["availability"] == "unverified" and row["side"] is None
    f.game.away_defencemen.remove(player)
    Game.objects.filter(pk=f.game.pk).update(gameday=None)
    rows = listing(client, ordering="date").json()["results"]
    assert rows[-1]["date"] is None and rows[-1]["availability"] == "missing"
    assert listing(client, date_min="2020-01-01").json()["count"] == 4


@pytest.mark.parametrize("raw", [{}, [], "bad"])
def test_malformed_logs_do_not_hide_verified_roster_membership(client, saved_games, raw):
    player = saved_games.players["away_forward"]
    Skater.objects.filter(pk=player.pk).update(gamelog_stats=raw)
    data = listing(client, search=player.name).json()
    assert data["count"] == 1 and data["results"][0]["availability"] == "missing"


def test_orphan_rows_without_saved_games_or_roster_are_never_trusted(client, saved_games):
    player = saved_games.players["away_forward"]
    player.refresh_from_db()
    player.gamelog_stats.update({"2025-01-01": None, "invalid": {}, "2026-02-30": {}})
    player.save(update_fields=["gamelog_stats"])
    saved_games.game.away_forwards.remove(player)
    data = listing(client, search=player.name).json()
    assert data["count"] == 3 and all(row["game"] is None for row in data["results"])
    assert all(value is None for row in data["results"] for value in row["stats"].values())
    assert (
        next(row for row in data["results"] if row["date"] == "2025-01-01")["availability"]
        == "missing"
    )
    assert listing(client, search=player.name, season_id="20262027").json()["count"] == 0


def test_history_filters_use_game_ids_not_sbs_or_calendar(client, saved_games):
    f = saved_games
    player = f.players["away_forward"]
    day = Gameday.objects.create(day="2025-01-01")
    game = Game.objects.create(nhl_id=2024029998, gameday=day)
    game.away_forwards.add(player)
    player.refresh_from_db()
    player.gamelog_stats[str(day.day)] = dict(
        player.gamelog_stats[f.day["date"]], gameId=game.nhl_id
    )
    player.sbs_stats = []
    player.save(update_fields=["gamelog_stats", "sbs_stats"])
    data = listing(client, season_id="20242025").json()
    assert data["count"] == 1 and data["results"][0]["game"]["nhl_id"] == game.nhl_id
    assert data["meta"]["season_id"] == "20242025"


def test_owned_rows_change_with_membership_and_do_not_leak_comparison_or_other_users(
    client, saved_games
):
    f = saved_games
    before = state([f.owner, f.other])
    client.force_login(f.other)
    assert {row["player"]["nhl_id"] for row in listing(client).json()["results"]} == {
        f.players["home_forward"].nhl_id
    }
    client.force_login(f.owner)
    player = f.players["away_forward"]
    target = reverse("api_v1:favorite-membership", args=["skater", player.nhl_id])
    assert client.delete(target).status_code == 204
    data = listing(client).json()
    assert {row["player"]["nhl_id"] for row in data["results"]} == {
        f.players["home_defense"].nhl_id
    }
    assert data["meta"]["quota"]["total_count"] == 2
    assert state([f.other])[f.other.pk] == before[f.other.pk]
    assert client.put(target).status_code == 201
    assert listing(client).json()["count"] == 4


def test_read_is_bounded_read_only_and_fetches_no_season_or_career_snapshots(
    client, saved_games, django_assert_num_queries, offline
):
    f = saved_games
    before = {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie, Game, Side)
    }
    memberships = state([f.owner, f.other])
    calls_before = offline.call_count
    from django.db import connection

    def queries(execute, sql, params, many, context):
        assert not any(
            token in sql.lower() for token in ("sbs_stats", "career_stats", '"goals"', '"saves"')
        )
        return execute(sql, params, many, context)

    with connection.execute_wrapper(queries), django_assert_num_queries(14):
        assert listing(client, ordering="player_name").status_code == 200
    with django_assert_num_queries(12):
        assert listing(client, player_type="goalie", ordering="player_nhl_id").status_code == 200
    assert before == {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie, Game, Side)
    }
    assert memberships == state([f.owner, f.other]) and offline.call_count == calls_before


def test_query_count_does_not_grow_with_favorites_and_games(
    client, saved_games, django_assert_num_queries
):
    f = saved_games
    prototype = f.players["away_forward"]
    prototype.refresh_from_db()
    players = []
    for index in range(12):
        players.append(
            Skater(
                nhl_id=990000 + index,
                name=f"Bulk {index}",
                games=0,
                last_name=f"Bulk {index}",
                birth_date="2000-01-01",
                gamelog_stats={
                    f.day["date"]: dict(
                        prototype.gamelog_stats[f.day["date"]], player={"nhl_id": 990000 + index}
                    )
                },
            )
        )
    Skater.objects.bulk_create(players)
    f.owner.favorite_skaters.add(*players)
    f.game.away_forwards.add(*players)
    for index in range(12):
        day = Gameday.objects.create(day=date(2026, 12, 1) + timedelta(days=index))
        game = Game.objects.create(nhl_id=2026028000 + index, gameday=day)
        game.home_forwards.add(*players)
    with django_assert_num_queries(14):
        data = listing(client, page_size=100).json()
    assert data["count"] == 160 and len(data["results"]) == 100


def test_ties_are_deterministic_across_player_insertion_and_page_boundaries(client, saved_games):
    players = [saved_games.players[key] for key in ("away_forward", "home_defense")]
    for player in players:
        Skater.objects.filter(pk=player.pk).update(last_name="Same", gamelog_stats={})
    first = listing(client, page_size=1).json()
    second = client.get(first["next"]).json()
    assert [
        first["results"][0]["player"]["nhl_id"],
        second["results"][0]["player"]["nhl_id"],
    ] == sorted(player.nhl_id for player in players)


def test_empty_selection_and_anonymous_access(client, saved_games, django_assert_num_queries):
    saved_games.owner.favorite_skaters.clear()
    with django_assert_num_queries(8):
        data = listing(client).json()
    assert (
        data["count"] == 0 and data["results"] == [] and data["meta"]["quota"]["total_count"] == 1
    )
    assert listing(client, page=2).status_code == 404
    client.logout()
    response = listing(client)
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "authentication_required"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"player_type": "both"},
        {"player_type": ""},
        {"player_type": ["skater", "goalie"]},
        {"goals_min": "nan"},
        {"goals_min": "2", "goals_max": "1"},
        {"player_type": "goalie", "goals_min": "1"},
        {"player_type": "skater", "saves_min": "1"},
        {"player_type": "skater", "ordering": "decision"},
        {"ordering": "gamelog_stats__goals"},
        {"season_id": "2026"},
        {"date_min": "2026-2-01"},
        {"date_min": "2026-11-02", "date_max": "2026-11-01"},
        {"mode": "averages"},
        {"owner": "1"},
        {"page_size": "101"},
        {"search": ""},
    ],
)
def test_invalid_queries_fail_without_membership_changes(client, saved_games, params):
    before = state([saved_games.owner, saved_games.other])
    assert listing(client, **params).status_code == 400
    assert before == state([saved_games.owner, saved_games.other])


def test_schema_private_read_contract_and_unsafe_methods(
    client, saved_games, django_assert_num_queries
):
    target = reverse("api_v1:favorites-gamelog")
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(target).status_code == 405
    head = client.head(target)
    assert head.status_code == 200 and head.content == b""
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    get = schema["paths"][target]["get"]
    assert get["security"] == [{"cookieAuth": []}]
    assert "player" in schema["components"]["schemas"]["FavoriteGamelogEntry"]["properties"]


@pytest.mark.django_db(transaction=True)
def test_gamelog_waits_for_favorite_removal_and_returns_updated_selection(client, saved_games):
    f = saved_games
    clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
    for strict in clients:
        strict.force_login(f.owner)
    tokens = [csrf(strict) for strict in clients]
    removed = f.players["away_forward"]
    target = reverse("api_v1:favorite-membership", args=["skater", removed.nhl_id])
    a, b = concurrent_changes(
        clients[0],
        ("delete", target, tokens[0]),
        clients[1],
        ("get", reverse("api_v1:favorites-gamelog"), tokens[1]),
    )
    assert a[0] == 204 and b[0] == 200
    assert {row["player"]["nhl_id"] for row in b[1]["results"]} == {
        f.players["home_defense"].nhl_id
    }
    assert b[1]["meta"]["quota"]["total_count"] == 2


def test_same_nhl_id_in_both_models_remains_a_typed_favorite(client, saved_games):
    skater = saved_games.players["away_forward"]
    goalie = saved_games.players["away_goalie"]
    goalie.refresh_from_db()
    goalie.nhl_id = skater.nhl_id
    goalie.gamelog_stats[saved_games.day["date"]]["player"]["nhl_id"] = skater.nhl_id
    goalie.save(update_fields=["nhl_id", "gamelog_stats"])
    skaters = listing(client).json()
    goalies = listing(client, player_type="goalie").json()
    assert goalies["count"] == 1
    row = goalies["results"][0]
    assert row["player"]["nhl_id"] == skater.nhl_id and row["player"]["player_type"] == "goalie"
    assert row["stats"]["saves"] == 24 and "goals" not in row["stats"]
    assert (
        next(row for row in linked(skaters) if row["player"]["nhl_id"] == skater.nhl_id)["stats"][
            "goals"
        ]
        == 1
    )
