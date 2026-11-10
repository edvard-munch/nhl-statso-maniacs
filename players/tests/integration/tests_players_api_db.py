"""Public catalogue contracts over existing season regression fixtures."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
import pytest

from players.models import Goalie, Skater
from players.season_stats import read_season_stats
from players.tests.integration.tests_players_season_table import (
    stored_rows,
    table_players,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def catalogue_players(table_players, season_stats_data):
    low, high = table_players["low"], table_players["high"]
    for row in low.sbs_stats:
        if row.get("season") == "2026-27":
            row["teamAbbr"] = "COL"
    low.save(update_fields=["sbs_stats"])
    high.sbs_stats[0]["plusMinus"] = 1
    high.save(update_fields=["sbs_stats"])
    goalie = Goalie.objects.create(
        nhl_id=table_players["low"].nhl_id,
        name="Catalogue Goalie",
        last_name="Goalie",
        birth_date="2000-01-01",
        games=999,
        wins=999,
        position_abbr="G",
        sbs_stats=stored_rows(season_stats_data["cases"]["current_goalie"]),
    )
    return {**table_players, "goalie": goalie}


def get(client, **params):
    return client.get(reverse("api_v1:players"), params)


def rows(client, **params):
    response = get(client, **params)
    assert response.status_code == 200, response.content
    return response.json()["results"]


def test_default_catalogue_uses_sbs_membership_statistics_and_public_allowlist(
    client, catalogue_players
):
    response = get(client)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"]
    data = response.json()
    assert data["count"] == 2
    assert data["meta"] == {
        "season_id": "20262027",
        "player_type": "skater",
        "mode": "totals",
        "ordering": "-points,last_name,nhl_id",
    }
    high, low = data["results"]
    assert high["nhl_id"] == catalogue_players["high"].nhl_id
    assert low["nhl_id"] == catalogue_players["low"].nhl_id
    assert (high["stats"]["games"], high["stats"]["goals"], high["stats"]["points"]) == (5, 4, 10)
    assert type(high["stats"]["goals"]) is int
    assert high["stats"]["hits"] is None and high["availability"] == "partial"
    assert high["stats"]["avg_toi_seconds"] == 540
    assert low["stats"]["goals"] == 2 and low["stats"]["games"] == 10
    assert set(high) == {
        "player_type",
        "nhl_id",
        "name",
        "last_name",
        "slug",
        "image_url",
        "nation_flag_url",
        "position_abbr",
        "position_name",
        "nation",
        "nation_abbr",
        "age",
        "birth_date",
        "weight_lb",
        "height_cm",
        "weight_kg",
        "draft_year",
        "draft_number",
        "rookie",
        "teams",
        "availability",
        "stats",
    }
    assert "999" not in str(high["stats"])
    assert high["image_url"].endswith("skater_default.png")


def test_averages_are_derived_and_toi_stays_per_game_seconds(client, catalogue_players):
    high, low = rows(client, mode="averages")
    assert high["stats"]["goals"] == 0.8 and low["stats"]["goals"] == 0.2
    assert high["stats"]["hits"] is None
    assert high["stats"]["games"] == 5
    assert high["stats"]["avg_toi_seconds"] == 540
    selected = rows(client, mode="averages", goals_min="0.5")
    assert [row["name"] for row in selected] == [high["name"]]


def test_historical_selection_and_empty_valid_season_do_not_fall_back(client, catalogue_players):
    historical = rows(client, season_id="20252026")
    assert any(row["nhl_id"] == catalogue_players["old"].nhl_id for row in historical)
    response = get(client, season_id="20302031").json()
    assert response["count"] == 0 and response["results"] == []
    assert response["meta"]["season_id"] == "20302031"


def test_default_comes_from_both_player_types_not_selected_type_or_calendar(
    client, catalogue_players
):
    Goalie.objects.filter(pk=catalogue_players["goalie"].pk).update(
        sbs_stats=[{"season": "2027-28", "gamesPlayed": 1}]
    )
    data = get(client).json()
    assert data["meta"]["season_id"] == "20272028" and data["results"] == []


def test_empty_database_has_null_season_and_empty_page(client):
    data = get(client).json()
    assert data["meta"]["season_id"] is None and data["count"] == 0
    assert data["next"] is data["previous"] is None
    assert get(client, page=2).status_code == 404


def test_season_teams_ignore_current_roster_and_team_filter_keeps_overall_totals(
    client, catalogue_players, season_stats_data
):
    low = catalogue_players["low"]
    assert [row["nhl_id"] for row in rows(client, team="COL")] == [low.nhl_id]
    Skater.objects.filter(pk=low.pk).update(
        sbs_stats=stored_rows(season_stats_data["cases"]["traded_skater"])
    )
    buf = next(row for row in rows(client, team="BUF") if row["nhl_id"] == low.nhl_id)
    col = next(row for row in rows(client, team="COL") if row["nhl_id"] == low.nhl_id)
    assert buf == col
    assert {team["abbr"] for team in col["teams"]} == {"BUF", "COL"}
    expected = read_season_stats(
        low.__class__.objects.get(pk=low.pk).sbs_stats, "20262027", player_type="skater"
    )
    assert col["stats"]["goals"] == expected.totals["goals"]


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"search": "  CURRENT LOW  "}, "low"),
        ({"team": "COL"}, "low"),
        ({"position": "D"}, "low"),
        ({"nation": "CAN"}, "low"),
        ({"rookie": "false"}, "low"),
        ({"rookie": "true"}, "high"),
        ({"goals_min": 3, "goals_max": 4}, "high"),
        ({"plus_minus_max": -2}, "low"),
        ({"age_min": 25}, "high"),
        ({"height_cm_max": 185}, "low"),
        ({"weight_kg_min": 90}, "low"),
        ({"weight_lb_min": 190}, "low"),
        ({"birth_date_max": "1999-12-31"}, "high"),
        ({"avg_toi_seconds_max": 600}, "high"),
    ],
)
def test_named_filters_use_projected_values_before_pagination(
    client, catalogue_players, params, expected
):
    data = get(client, **params, page_size=1).json()
    assert data["count"] == 1
    assert [row["nhl_id"] for row in data["results"]] == [catalogue_players[expected].nhl_id]


def test_csv_filters_or_within_field_and_and_between_fields(client, catalogue_players):
    assert len(rows(client, position="C,D", team="BUF,COL")) == 2
    assert len(rows(client, position="C,D", nation="CAN")) == 1
    assert rows(client, search="%") == []
    assert rows(client, search="Current.*") == []
    assert rows(client, hits_min=0)[0]["nhl_id"] == catalogue_players["low"].nhl_id


@pytest.mark.parametrize("ordering", ["hits", "-hits"])
def test_unknowns_sort_last_in_both_directions(client, catalogue_players, ordering):
    result = rows(client, ordering=ordering)
    assert result[-1]["nhl_id"] == catalogue_players["high"].nhl_id


def test_ordering_and_pagination_are_global_stable_and_preserve_filters(client, catalogue_players):
    first = get(client, ordering="goals", page_size=1, position="D,C").json()
    second = client.get(first["next"]).json()
    assert first["results"][0]["nhl_id"] == catalogue_players["low"].nhl_id
    assert second["results"][0]["nhl_id"] == catalogue_players["high"].nhl_id
    assert first["meta"] == second["meta"]
    assert "position=D%2CC" in first["next"]
    assert get(client, page=3, page_size=1).status_code == 404
    low, high = catalogue_players["low"], catalogue_players["high"]
    Skater.objects.filter(pk__in=[low.pk, high.pk]).update(last_name="Same")
    assert [row["nhl_id"] for row in rows(client, ordering="last_name")] == [1, 2]


def test_goalie_type_is_explicit_with_rates_and_no_skater_stats(client, catalogue_players):
    goalie = catalogue_players["goalie"]
    data = get(client, player_type="goalie").json()
    assert data["count"] == 1 and data["meta"]["ordering"] == "-wins,last_name,nhl_id"
    row = data["results"][0]
    expected = read_season_stats(goalie.sbs_stats, "20262027", player_type="goalie")
    assert row["nhl_id"] == 1 and row["player_type"] == "goalie"
    assert row["stats"]["wins"] == expected.totals["wins"] != 999
    assert row["stats"]["save_percentage"] == expected.totals["saves_perc"]
    assert row["stats"]["shutouts"] == expected.totals["shotouts"]
    assert "goals" not in row["stats"] and "shotouts" not in row["stats"]
    assert rows(client, player_type="goalie", wins_min=100) == []


@pytest.mark.parametrize(
    "damage",
    [
        None,
        {},
        [None],
        [{"season": "2026-27", "gamesPlayed": 1}, {"season": "2026-27", "gamesPlayed": 2}],
    ],
)
def test_malformed_or_ambiguous_sbs_never_uses_snapshot(client, catalogue_players, damage):
    Skater.objects.filter(pk=catalogue_players["high"].pk).update(sbs_stats=damage)
    assert [row["nhl_id"] for row in rows(client)] == [catalogue_players["low"].nhl_id]


@pytest.mark.parametrize(
    "params",
    [
        {"season_id": "2026-27"},
        {"season_id": "20262028"},
        {"season_id": " 20262027"},
        {"player_type": "all"},
        {"mode": "career"},
        {"player_type": "goalie", "mode": "averages"},
        {"player_type": "goalie", "goals_min": 1},
        {"wins_min": 1},
        {"ordering": "team__name"},
        {"ordering": "sbs_stats"},
        {"ordering": "-wins"},
        {"ordering": "goals,-goals"},
        {"ordering": "goals,"},
        {"goals_min": "NaN"},
        {"goals_max": "inf"},
        {"goals_min": 5, "goals_max": 1},
        {"page": ""},
        {"page": 0},
        {"page_size": 101},
        {"mode": ""},
        {"rookie": "yes"},
        {"rookie": ""},
        {"team": "BUF,,COL"},
        {"nation": "CAN,CAN"},
        {"search": " "},
        {"unknown": "x"},
        {"birth_date_min": "2026-2-01"},
        {"birth_date_min": "2000-01-01", "birth_date_max": "1990-01-01"},
        {"hits_isnull": "yes"},
        {"wins_isnull": "true"},
    ],
)
def test_invalid_queries_return_typed_400_before_database_access(
    client, params, django_assert_num_queries
):
    with django_assert_num_queries(0):
        response = get(client, **params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameters"


def test_duplicate_query_is_rejected_before_database_access(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get(reverse("api_v1:players") + "?mode=totals&mode=averages")
    assert response.status_code == 400


def test_read_only_queries_are_bounded_and_defer_snapshots_histories(
    client, catalogue_players, offline, django_assert_num_queries
):
    before = {model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie)}

    def select_only(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith(("SELECT", "DECLARE"))
        assert "for update" not in sql.lower() and "advisory" not in sql.lower()
        for field in ("career_stats", "gamelog_stats", "sbs_stats_avg", "favoriting", "comparing"):
            assert field not in sql
        return execute(sql, params, many, context)

    with connection.execute_wrapper(select_only), django_assert_num_queries(2):
        response = get(client, season_id="20262027")
    assert response.status_code == 200 and not offline.called
    assert before == {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie)
    }
    with django_assert_num_queries(4):
        assert get(client).status_code == 200


def test_public_rows_do_not_include_user_memberships_notes_or_positions(client, catalogue_players):
    public = get(client).json()
    user = get_user_model().objects.create_user(username="catalogue-private")
    user.favorite_skaters.add(catalogue_players["low"])
    user.comparable_skaters.add(catalogue_players["high"])
    client.force_login(user)
    assert get(client).json() == public
    assert "favorit" not in str(public) and "comparing" not in str(public)


def test_head_and_json_method_errors(client):
    response = client.head(reverse("api_v1:players"))
    assert response.status_code == 200 and response.content == b""
    assert (
        client.post(reverse("api_v1:players"), {}, content_type="application/json").status_code
        == 405
    )
    assert client.get(reverse("api_v1:players"), HTTP_ACCEPT="text/html").status_code == 406


def test_openapi_contains_typed_statistics_filters_and_public_access(client):
    schema = client.get(reverse("api_v1:schema")).json()
    op = schema["paths"]["/api/v1/players/"]["get"]
    assert op["operationId"] == "players_list" and op.get("security", []) in ([], [{}])
    params = {param["name"]: param for param in op["parameters"]}
    assert {
        "season_id",
        "player_type",
        "mode",
        "ordering",
        "goals_min",
        "wins_max",
        "page_size",
    } <= params.keys()
    assert params["page_size"]["schema"]["maximum"] == 100
    schemas = schema["components"]["schemas"]
    assert len(schemas["CatalogueSeasonStatistics"]["oneOf"]) == 3
    assert schemas["CatalogueSeasonStatistics"]["discriminator"]["propertyName"] == "kind"
    assert "kind" in schemas["SkaterTotals"]["required"]
    assert "kind" in schemas["SkaterAverages"]["required"]
    assert "kind" in schemas["GoalieSeason"]["required"]
    assert schemas["SkaterTotals"]["properties"]["goals"]["type"] == "integer"
    assert schemas["SkaterAverages"]["properties"]["goals"]["type"] == "number"
    assert schemas["GoalieSeason"]["properties"]["save_percentage"]["nullable"]


@pytest.mark.parametrize(
    "query,expected", [({"hits_isnull": "true"}, "high"), ({"hits_isnull": "false"}, "low")]
)
def test_missing_value_filters_are_explicit(client, catalogue_players, query, expected):
    assert [row["nhl_id"] for row in rows(client, **query)] == [catalogue_players[expected].nhl_id]


def test_stats_discriminators_and_known_zero_times_counts(client, catalogue_players):
    low = catalogue_players["low"]
    low.sbs_stats[1].update(goals=0, hits=0, avgToi="00:00", plusMinus=-3)
    low.save(update_fields=["sbs_stats"])
    row = next(row for row in rows(client) if row["nhl_id"] == low.nhl_id)
    assert row["stats"]["kind"] == "skater_totals"
    assert row["stats"]["goals"] == row["stats"]["hits"] == row["stats"]["avg_toi_seconds"] == 0
    assert row["stats"]["plus_minus"] == -3
    assert rows(client, mode="averages")[0]["stats"]["kind"] == "skater_averages"
    assert rows(client, player_type="goalie")[0]["stats"]["kind"] == "goalie_totals"


@pytest.mark.parametrize(
    "field,bad", [("goals", -1), ("hits", 1.5), ("goals", True), ("powerPlayTimeOnIce", "bad")]
)
def test_invalid_saved_values_are_null_instead_of_coerced_or_zeroed(
    client, catalogue_players, field, bad
):
    low = catalogue_players["low"]
    low.sbs_stats[1][field] = bad
    low.save(update_fields=["sbs_stats"])
    target = {"goals": "goals", "hits": "hits", "powerPlayTimeOnIce": "avg_pp_toi_seconds"}[field]
    row = next(row for row in rows(client) if row["nhl_id"] == low.nhl_id)
    assert row["stats"][target] is None and row["availability"] == "partial"
    average = next(row for row in rows(client, mode="averages") if row["nhl_id"] == low.nhl_id)
    assert average["stats"][target] is None


def test_unknown_season_team_remains_usable_without_invented_identity(client, catalogue_players):
    low = catalogue_players["low"]
    low.sbs_stats[1]["teamAbbr"] = "XYZ"
    low.save(update_fields=["sbs_stats"])
    row = rows(client, team="XYZ")[0]
    assert row["teams"] == [{"abbr": "XYZ", "name": "XYZ", "nhl_id": None, "slug": None}]


def test_goalie_split_rates_keep_unknown_denominator_null(client, catalogue_players):
    goalie = catalogue_players["goalie"]
    goalie.sbs_stats = [
        {
            "season": "2026-27",
            "teamAbbr": "BUF",
            "gamesPlayed": 2,
            "wins": 1,
            "saves": 18,
            "shotsAgainst": 20,
        },
        {
            "season": "2026-27",
            "teamAbbr": "COL",
            "gamesPlayed": 3,
            "wins": 2,
            "saves": 27,
            "shotsAgainst": 30,
        },
    ]
    goalie.save(update_fields=["sbs_stats"])
    row = rows(client, player_type="goalie")[0]
    assert row["stats"]["games"] == 5 and row["stats"]["wins"] == 3
    assert row["stats"]["save_percentage"] == 0.9
    assert row["stats"]["goals_against_average"] is None
    assert row["stats"]["shutouts"] is None


def test_query_count_stays_bounded_for_many_players_and_only_page_is_serialized(
    client, catalogue_players, django_assert_num_queries, monkeypatch
):
    low = catalogue_players["low"]
    for index in range(10, 65):
        Skater.objects.create(
            nhl_id=index,
            name=f"Bulk {index}",
            last_name="Bulk",
            birth_date="2000-01-01",
            games=0,
            sbs_stats=low.sbs_stats,
        )
    calls = []
    from players.api.catalogue_serializers import CataloguePlayerSerializer

    original = CataloguePlayerSerializer.get_image_url

    def image_url(self, row):
        calls.append(row["nhl_id"])
        return original(self, row)

    monkeypatch.setattr(CataloguePlayerSerializer, "get_image_url", image_url)
    with django_assert_num_queries(2):
        data = get(client, season_id="20262027").json()
    assert data["count"] == 57 and len(data["results"]) == len(calls) == 50
    assert len(rows(client, season_id="20262027", page_size=100)) == 57
