"""Public typed profiles, season history and verified gamelogs over saved fixtures."""

from copy import deepcopy
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
import pytest

from players.models import Game, Gameday, Goalie, Side, Skater, Team
from players.tests.integration.tests_team_season_tables import team_players  # noqa: F401
from players.tests.integration.tests_game_pages_db import game_page  # noqa: F401
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def profiles(team_players):
    skater = team_players["defender"]
    skater.career_stats = {
        "gamesPlayed": 90,
        "goals": 22,
        "hits": 68,
        "powerPlayTimeOnIcePerGame": "02:05",
    }
    skater.career_stats_avg = {"gamesPlayed": 90, "goals": 0.24, "hits": 0.76}
    skater.save(update_fields=["career_stats", "career_stats_avg"])
    goalie = team_players["goalie"]
    goalie.career_stats = {
        "gamesPlayed": 40,
        "wins": 20,
        "losses": 15,
        "otLosses": 5,
        "goalsAgainstAvg": 2.125,
        "savePctg": 0.9123,
        "shotsAgainst": 1300,
        "goalsAgainst": 66,
        "shutouts": 3,
    }
    goalie.save(update_fields=["career_stats"])
    return team_players


def url(route="player-detail", player_type="skater", nhl_id=1):
    return reverse("api_v1:" + route, kwargs={"player_type": player_type, "nhl_id": nhl_id})


def get(client, route="player-detail", player_type="skater", nhl_id=1, **params):
    return client.get(url(route, player_type, nhl_id), params)


def test_profile_keeps_current_identity_season_and_career_separate(client, profiles):
    response = get(client)
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    data = response.json()
    assert data["meta"] == {"season_id": "20262027", "mode": "totals", "player_type": "skater"}
    assert data["player"]["nhl_id"] == 1 and data["player"]["jersey_number"] == 10
    assert data["current_team"]["abbr"] == "BUF"
    assert data["selected_season"]["stats"]["goals"] == 2
    assert data["career_totals"]["stats"]["games"] == 90
    assert data["career_totals"]["stats"]["goals"] == 22
    assert data["career_totals"]["stats"]["avg_pp_toi_seconds"] == 125
    assert data["career_averages"]["stats"]["goals"] == 0.24
    assert data["career_averages"]["stats"]["hits"] == 0.76
    assert data["career_averages"]["stats"]["assists"] is None
    assert "999" not in str(data["selected_season"])
    assert client.get(data["seasons_url"]).status_code == 200
    assert data["gamelog_url"] == url("player-gamelog")


def test_selected_season_modes_and_missing_selection_do_not_rewrite_career(client, profiles):
    default = get(client).json()
    average = get(client, mode="averages").json()
    assert average["selected_season"]["stats"]["goals"] == 0.2
    assert average["selected_season"]["stats"]["kind"] == "skater_averages"
    assert average["career_totals"] == default["career_totals"]
    missing = get(client, season_id="20302031").json()
    assert missing["selected_season"] == {"availability": "missing", "stats": None}
    assert missing["career_totals"] == default["career_totals"]
    old = get(client, season_id="20252026").json()
    assert old["selected_season"]["stats"]["goals"] == 20


def test_known_profile_without_positive_season_games_or_team_still_exists(client, profiles):
    Skater.objects.filter(nhl_id=1).update(
        sbs_stats=[], career_stats={}, career_stats_avg={}, team=None, games=999
    )
    data = get(client).json()
    assert data["player"]["nhl_id"] == 1 and data["current_team"] is None
    assert data["selected_season"]["stats"] is None
    assert data["career_totals"]["stats"] is None and data["career_averages"]["stats"] is None
    rows = deepcopy(profiles["defender"].sbs_stats)
    rows[1]["gamesPlayed"] = 0
    Skater.objects.filter(nhl_id=1).update(sbs_stats=[rows[1]])
    zero = get(client).json()
    assert zero["selected_season"]["stats"]["games"] == 0
    assert get(client, mode="averages").json()["selected_season"]["stats"]["goals"] is None


def test_goalie_career_and_selected_season_remain_typed_and_rates_keep_saved_precision(
    client, profiles
):
    data = get(client, player_type="goalie", nhl_id=10).json()
    assert data["career_averages"] is None
    assert data["career_totals"]["stats"]["wins"] == 20
    assert data["career_totals"]["stats"]["save_percentage"] == 0.9123
    assert data["career_totals"]["stats"]["saves"] == 1234
    assert data["selected_season"]["stats"]["wins"] == 3
    assert data["career_totals"]["stats"]["kind"] == "goalie_totals"


def test_skater_and_goalie_with_same_nhl_id_remain_distinct(client, profiles):
    Goalie.objects.create(nhl_id=1, name="Typed Goalie", birth_date="2000-01-01", games=0)
    assert get(client).json()["player"]["name"] == "Season Defender"
    assert get(client, player_type="goalie").json()["player"]["name"] == "Typed Goalie"


def test_season_history_is_newest_first_with_overall_and_exact_contributions(client, profiles):
    data = get(client, "player-seasons", nhl_id=2).json()
    season = data["results"][0]
    assert season["season_id"] == "20262027" and season["stats"]["games"] == 10
    assert season["stats"]["goals"] == 4
    splits = {row["team"]["abbr"]: row for row in season["contributions"]}
    assert splits["BUF"]["stats"]["games"] == 6 and splits["BUF"]["stats"]["goals"] == 3
    assert splits["COL"]["stats"]["games"] == 4 and splits["COL"]["stats"]["goals"] == 1
    average = get(client, "player-seasons", nhl_id=2, mode="averages").json()["results"][0]
    assert average["stats"]["goals"] == 0.4
    assert (
        next(row for row in average["contributions"] if row["team"]["abbr"] == "BUF")["stats"][
            "goals"
        ]
        == 0.5
    )
    first = get(client, "player-seasons", page_size=1).json()
    second = client.get(first["next"]).json()
    assert (
        first["results"][0]["season_id"] == "20262027"
        and second["results"][0]["season_id"] == "20252026"
    )
    assert first["meta"] == second["meta"]
    assert get(client, "player-seasons", page=99).status_code == 404


def test_history_combined_total_does_not_replace_a_missing_or_ambiguous_team_split(
    client, profiles
):
    player = profiles["traded"]
    combined = dict(player.sbs_stats[0], teamAbbr="TOT", gamesPlayed=20, goals=8)
    player.sbs_stats += [combined, deepcopy(player.sbs_stats[0])]
    player.save(update_fields=["sbs_stats"])
    row = get(client, "player-seasons", nhl_id=2).json()["results"][0]
    assert row["stats"]["goals"] == 8
    ambiguous = next(
        split
        for split in row["contributions"]
        if split["team"]["abbr"] == player.sbs_stats[0]["teamAbbr"]
    )
    assert ambiguous["availability"] == "unverified" and ambiguous["stats"] is None


@pytest.mark.parametrize(
    "raw",
    [None, {}, [None], [{"season": "20262028"}], [{"season": "2026-27", "leagueAbbrev": "AHL"}]],
)
def test_malformed_or_non_nhl_history_returns_empty_without_snapshots(client, profiles, raw):
    Skater.objects.filter(nhl_id=1).update(sbs_stats=raw)
    assert get(client, "player-seasons").json()["results"] == []


def test_ambiguous_selected_season_remains_explicitly_unverified(client, profiles):
    player = profiles["defender"]
    player.sbs_stats += [deepcopy(player.sbs_stats[1])]
    player.save(update_fields=["sbs_stats"])
    assert get(client).json()["selected_season"] == {"availability": "unverified", "stats": None}


def test_profile_reads_only_allowed_fields_and_is_identical_for_signed_in_viewer(
    client, profiles, django_assert_num_queries, offline
):
    before = {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie, Team)
    }

    def select_only(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith(("SELECT", "DECLARE"))
        for token in (
            "gamelog_stats",
            "sbs_stats_avg",
            "favoriting",
            "comparing",
            "proj_stats",
            "for update",
            "advisory",
        ):
            assert token not in sql.lower()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(select_only), django_assert_num_queries(1):
        public = get(client, season_id="20262027").json()
    with django_assert_num_queries(3):
        get(client)
    with django_assert_num_queries(2):
        history = get(client, "player-seasons").json()
    assert before == {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie, Team)
    }
    user = get_user_model().objects.create_user(username="private-profile-viewer")
    user.favorite_skaters.add(profiles["defender"])
    client.force_login(user)
    assert get(client, season_id="20262027").json() == public
    assert get(client, "player-seasons").json() == history
    assert "favorit" not in str(public) and "_player" not in str(public)
    assert not offline.called


def test_gamelog_matches_saved_game_detail_values_and_verification(client, game_page, monkeypatch):
    monkeypatch.setattr(
        "players.api.player_logs.timezone.now", lambda: datetime(2026, 11, 10, tzinfo=timezone.utc)
    )
    f = game_page
    player = f.players["away_forward"]
    response = get(client, "player-gamelog", nhl_id=player.nhl_id)
    assert response.status_code == 200, response.content
    data = response.json()
    row = next(row for row in data["results"] if row["game"])
    game = client.get(reverse("api_v1:game-detail", args=[f.game.nhl_id])).json()
    expected = game["rosters"]["away"]["forwards"][0]
    assert row["stats"] == expected["stats"]
    assert row["availability"] == expected["availability"]
    assert row["stats"]["pp_toi_seconds"] == 61 and row["stats"]["sh_toi_seconds"] == 121
    assert row["side"] == "away" and row["team"]["nhl_id"] == f.away.nhl_id
    assert row["opponent"]["nhl_id"] == f.home.nhl_id
    assert row["game"]["nhl_id"] == f.game.nhl_id


def test_goalie_gamelog_uses_typed_identity_and_saved_fraction(client, game_page):
    player = game_page.players["away_goalie"]
    row = next(
        row
        for row in get(client, "player-gamelog", player_type="goalie", nhl_id=player.nhl_id).json()[
            "results"
        ]
        if row["game"]
    )
    assert row["stats"]["save_percentage"] == 0.923 and row["stats"]["saves"] == 24
    assert row["stats"]["toi_seconds"] == 3600 and "goals" not in row["stats"]


@pytest.mark.parametrize(
    "damage,availability",
    [
        ("wrong_player", "unverified"),
        ("wrong_game", "unverified"),
        ("wrong_type", "unverified"),
        ("missing", "missing"),
    ],
)
def test_gamelog_never_trusts_a_wrong_date_row(client, game_page, damage, availability):
    player = game_page.players["away_forward"]
    player.refresh_from_db()
    row = player.gamelog_stats[game_page.day["date"]]
    if damage == "wrong_player":
        row["player"]["nhl_id"] = 999999
    elif damage == "wrong_game":
        row["gameId"] = game_page.game.nhl_id + 1
    elif damage == "wrong_type":
        row["position"] = "G"
    else:
        player.gamelog_stats.pop(game_page.day["date"])
    player.save(update_fields=["gamelog_stats"])
    saved = next(
        row
        for row in get(client, "player-gamelog", nhl_id=player.nhl_id).json()["results"]
        if row["game"]
    )
    assert saved["availability"] == availability
    assert all(value is None for value in saved["stats"].values())


def test_orphan_rows_are_unverified_invalid_dates_are_skipped_and_filters_precede_pagination(
    client, game_page
):
    player = game_page.players["away_forward"]
    player.refresh_from_db()
    prototype = deepcopy(player.gamelog_stats[game_page.day["date"]])
    player.gamelog_stats = {
        game_page.day["date"]: prototype,
        "2026-01-01": prototype,
        "2025-01-01": prototype,
        "invalid": prototype,
        "2026-02-30": prototype,
    }
    player.save(update_fields=["gamelog_stats"])
    data = get(
        client, "player-gamelog", nhl_id=player.nhl_id, date_max="2026-01-01", page_size=1
    ).json()
    assert data["count"] == 2 and data["results"][0]["date"] == "2026-01-01"
    orphan = data["results"][0]
    assert orphan["game"] is None and orphan["availability"] == "unverified"
    assert all(value is None for value in orphan["stats"].values())
    assert client.get(data["next"]).json()["results"][0]["date"] == "2025-01-01"
    oldest = get(client, "player-gamelog", nhl_id=player.nhl_id, ordering="date").json()["results"][
        0
    ]
    assert oldest["date"] == "2025-01-01"
    season = get(client, "player-gamelog", nhl_id=player.nhl_id, season_id="20262027").json()
    assert all(row["game"] for row in season["results"])


def test_legacy_collision_and_duplicate_roster_membership_are_unverified(client, game_page):
    player = game_page.players["away_forward"]
    player.refresh_from_db()
    player.gamelog_stats[game_page.day["date"]].pop("gameId", None)
    player.save(update_fields=["gamelog_stats"])
    other = Game.objects.create(nhl_id=2026029998, gameday=game_page.game.gameday)
    other.home_forwards.add(player)
    rows = get(client, "player-gamelog", nhl_id=player.nhl_id).json()["results"]
    assert all(row["availability"] == "unverified" for row in rows if row["game"])
    other.delete()
    game_page.game.away_defencemen.add(player)
    row = next(
        row
        for row in get(client, "player-gamelog", nhl_id=player.nhl_id).json()["results"]
        if row["game"]
    )
    assert row["availability"] == "unverified" and row["side"] is None


def test_gamelog_queries_are_bounded_read_only_and_signed_in_data_is_public(
    client, game_page, django_assert_num_queries, monkeypatch, offline
):
    monkeypatch.setattr(
        "players.api.player_logs.timezone.now", lambda: datetime(2026, 11, 10, tzinfo=timezone.utc)
    )
    player = game_page.players["away_forward"]
    before = list(Skater.objects.order_by("pk").values())
    calls_before = offline.call_count

    def select_only(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith("SELECT")
        for token in ("career_stats", "sbs_stats", "favoriting", "for update", "advisory"):
            assert token not in sql.lower()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(select_only), django_assert_num_queries(3):
        public = get(client, "player-gamelog", nhl_id=player.nhl_id).json()
    assert before == list(Skater.objects.order_by("pk").values())
    user = get_user_model().objects.create_user(username="public-log-viewer")
    client.force_login(user)
    assert get(client, "player-gamelog", nhl_id=player.nhl_id).json() == public
    assert offline.call_count == calls_before


@pytest.mark.parametrize(
    "route,params",
    [
        ("player-detail", {"mode": ""}),
        ("player-detail", {"season_id": "2026-27"}),
        ("player-detail", {"season_id": "20262028"}),
        ("player-detail", {"ordering": "goals"}),
        ("player-seasons", {"season_id": "20262027"}),
        ("player-seasons", {"page": 0}),
        ("player-seasons", {"page_size": 101}),
        ("player-seasons", {"mode": "bad"}),
        ("player-gamelog", {"ordering": "private"}),
        ("player-gamelog", {"date_min": "2026-2-01"}),
        ("player-gamelog", {"date_min": "2026-01-01", "date_max": "2025-01-01"}),
        ("player-gamelog", {"mode": "totals"}),
        ("player-gamelog", {"page_size": ""}),
    ],
)
def test_invalid_queries_are_typed_400_before_lookup(
    client, route, params, django_assert_num_queries
):
    with django_assert_num_queries(0):
        response = get(client, route, **params)
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"


@pytest.mark.parametrize("route", ["player-detail", "player-seasons", "player-gamelog"])
def test_duplicate_queries_fail_before_lookup(client, route, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get(url(route) + "?page=1&page=2")
    assert response.status_code == 400


@pytest.mark.parametrize("route", ["player-detail", "player-seasons", "player-gamelog"])
@pytest.mark.parametrize(
    "player_type,nhl_id",
    [("bad", 1), ("skater", 0), ("goalie", 999999), ("skater", 2**31), ("goalie", 10**30)],
)
def test_missing_or_wrong_typed_identity_returns_404(client, route, player_type, nhl_id):
    response = get(client, route, player_type, nhl_id)
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("route", ["player-detail", "player-seasons", "player-gamelog"])
def test_get_head_only_and_public_json_errors(client, profiles, route):
    response = client.head(url(route))
    assert (
        response.status_code == 200
        and response.content == b""
        and "no-store" in response["Cache-Control"]
    )
    assert client.post(url(route), {}, content_type="application/json").status_code == 405
    assert client.get(url(route), HTTP_ACCEPT="text/html").status_code == 406


def test_openapi_declares_nullable_profile_stats_history_and_game_dates(client):
    schema = client.get(reverse("api_v1:schema")).json()
    for suffix in ("", "seasons/", "gamelog/"):
        operation = schema["paths"]["/api/v1/players/{player_type}/{nhl_id}/" + suffix]["get"]
        assert operation.get("security", []) in ([], [{}])
        params = {param["name"]: param for param in operation["parameters"]}
        assert set(params["player_type"]["schema"]["enum"]) == {"skater", "goalie"}
    schemas = schema["components"]["schemas"]
    assert schemas["StatisticsPacket"]["properties"]["stats"]["nullable"]
    assert schemas["ProfileSkaterTotals"]["properties"]["games"]["nullable"]
    assert schemas["GamelogGame"]["properties"]["date"]["nullable"]


def test_unstamped_unique_legacy_row_is_verified_but_stamped_same_date_row_belongs_to_only_one_game(
    client, game_page
):
    player = game_page.players["away_forward"]
    player.refresh_from_db()
    row = player.gamelog_stats[game_page.day["date"]]
    row.pop("gameId", None)
    player.save(update_fields=["gamelog_stats"])
    saved = next(
        row
        for row in get(client, "player-gamelog", nhl_id=player.nhl_id).json()["results"]
        if row["game"]
    )
    assert saved["availability"] in ("complete", "partial") and saved["stats"]["goals"] == 1
    row["gameId"] = game_page.game.nhl_id
    player.save(update_fields=["gamelog_stats"])
    other = Game.objects.create(nhl_id=2026029998, gameday=game_page.game.gameday)
    other.away_forwards.add(player)
    data = get(client, "player-gamelog", nhl_id=player.nhl_id).json()["results"]
    correct = next(
        row for row in data if row["game"] and row["game"]["nhl_id"] == game_page.game.nhl_id
    )
    wrong = next(row for row in data if row["game"] and row["game"]["nhl_id"] == other.nhl_id)
    assert correct["stats"]["goals"] == 1 and wrong["availability"] == "unverified"
    assert all(value is None for value in wrong["stats"].values())


def test_undated_linked_game_is_missing_and_sorts_after_known_dates(client, game_page):
    player = game_page.players["away_forward"]
    Game.objects.filter(pk=game_page.game.pk).update(gameday=None)
    data = get(client, "player-gamelog", nhl_id=player.nhl_id).json()
    row = data["results"][-1]
    assert row["date"] is None and row["game"]["date"] is None
    assert row["availability"] == "missing"
    assert all(value is None for value in row["stats"].values())
    assert all(
        row["date"] is not None
        for row in get(
            client, "player-gamelog", nhl_id=player.nhl_id, date_min="2026-01-01"
        ).json()["results"]
    )


def test_a_game_stamp_without_roster_membership_cannot_verify_orphan_statistics(client, game_page):
    player = game_page.players["away_forward"]
    game_page.game.away_forwards.remove(player)
    data = get(client, "player-gamelog", nhl_id=player.nhl_id).json()
    assert all(row["game"] is None for row in data["results"])
    assert all(row["availability"] == "unverified" for row in data["results"])
    assert all(value is None for row in data["results"] for value in row["stats"].values())


@pytest.mark.parametrize("raw", [{}, [], "bad"])
def test_empty_or_malformed_log_is_safe_and_does_not_erase_known_game_membership(
    client, game_page, raw
):
    player = game_page.players["away_forward"]
    Skater.objects.filter(pk=player.pk).update(gamelog_stats=raw if raw is not None else {})
    data = get(client, "player-gamelog", nhl_id=player.nhl_id).json()
    assert data["count"] == 1 and data["results"][0]["availability"] == "missing"
    assert get(client, "player-gamelog", nhl_id=player.nhl_id, page=2).status_code == 404


@pytest.mark.parametrize("route", ["player-detail", "player-seasons"])
def test_goalie_average_mode_fails_before_lookup(client, route, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = get(client, route, player_type="goalie", nhl_id=10, mode="averages")
    assert response.status_code == 400


@pytest.mark.parametrize(
    "field,value", [("goals", -1), ("hits", 0.5), ("shots", True), ("assists", 10**400)]
)
def test_invalid_career_values_stay_null_without_using_snapshot_fields(
    client, profiles, field, value
):
    skater = profiles["defender"]
    skater.career_stats[field] = value
    skater.save(update_fields=["career_stats"])
    target = "shots_on_goal" if field == "shots" else field
    assert get(client).json()["career_totals"]["stats"][target] is None


def test_history_keeps_unknown_teams_and_zero_game_rows_without_inventing_averages(
    client, profiles
):
    player = profiles["defender"]
    player.sbs_stats = [{"season": "2026-27", "teamAbbr": "XYZ", "gamesPlayed": 0, "goals": 0}]
    player.save(update_fields=["sbs_stats"])
    row = get(client, "player-seasons", mode="averages").json()["results"][0]
    assert row["stats"]["games"] == 0 and row["stats"]["goals"] is None
    assert row["contributions"][0]["team"] == {
        "abbr": "XYZ",
        "nhl_id": None,
        "name": "XYZ",
        "slug": None,
    }


def test_history_page_sizes_and_queries_do_not_grow_with_seasons(
    client, profiles, django_assert_num_queries
):
    player = profiles["defender"]
    player.sbs_stats = [
        {"season": f"{year}{year + 1}", "teamAbbr": "BUF", "gamesPlayed": 1, "goals": 0}
        for year in range(1900, 2001)
    ]
    player.save(update_fields=["sbs_stats"])
    with django_assert_num_queries(2):
        data = get(client, "player-seasons").json()
    assert data["count"] == 101 and len(data["results"]) == 50
    assert len(get(client, "player-seasons", page_size=100).json()["results"]) == 100


def test_gamelog_queries_do_not_grow_with_games_or_date_rows(
    client, game_page, django_assert_num_queries
):
    player = game_page.players["away_forward"]
    player.refresh_from_db()
    prototype = deepcopy(player.gamelog_stats[game_page.day["date"]])
    for index in range(1, 56):
        year = 1900 + index
        day = Gameday.objects.create(day=f"{year}-11-01")
        game = Game.objects.create(nhl_id=int(f"{year}020001"), gameday=day)
        game.away_forwards.add(player)
        Side.objects.create(
            nhl_side_id=1000 + index * 2, game=game, team=game_page.away, side="away"
        )
        Side.objects.create(
            nhl_side_id=1001 + index * 2, game=game, team=game_page.home, side="home"
        )
        player.gamelog_stats[str(day.day)] = dict(prototype, gameId=game.nhl_id)
    player.save(update_fields=["gamelog_stats"])
    with django_assert_num_queries(3):
        data = get(client, "player-gamelog", nhl_id=player.nhl_id).json()
    assert data["count"] >= 56 and len(data["results"]) == 50 and data["next"]
    assert (
        len(get(client, "player-gamelog", nhl_id=player.nhl_id, page_size=100).json()["results"])
        == data["count"]
    )


def test_gamelog_named_statistic_filters_and_ordering_precede_pagination(client, game_page):
    player = game_page.players["away_forward"]
    row = get(
        client,
        "player-gamelog",
        nhl_id=player.nhl_id,
        goals_min=1,
        team="NJD",
        ordering="-pp_toi_seconds",
        page_size=1,
    ).json()
    assert row["count"] == 1 and row["results"][0]["stats"]["goals"] == 1
    assert get(client, "player-gamelog", nhl_id=player.nhl_id, goals_min=2).json()["count"] == 0
    assert all(
        row["stats"]["goals"] is None
        for row in get(client, "player-gamelog", nhl_id=player.nhl_id, goals_isnull="true").json()[
            "results"
        ]
    )
    for ordering in ("goals", "-goals"):
        data = get(client, "player-gamelog", nhl_id=player.nhl_id, ordering=ordering).json()
        assert data["results"][0]["stats"]["goals"] == 1


@pytest.mark.parametrize(
    "params",
    [
        {"goals_min": "NaN"},
        {"goals_min": 2, "goals_max": 1},
        {"ordering": "goals,-goals"},
        {"saves_min": 1},
        {"opponent": ""},
        {"goals_isnull": "yes"},
    ],
)
def test_bad_gamelog_statistic_filters_fail_before_lookup(
    client, params, django_assert_num_queries
):
    with django_assert_num_queries(0):
        response = get(client, "player-gamelog", **params)
    assert response.status_code == 400
