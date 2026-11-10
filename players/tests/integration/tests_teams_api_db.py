"""Saved team identity and exact season contributions over shared fixtures."""

from copy import deepcopy
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
import pytest

from players.models import Goalie, Skater, Team
from players.tests.integration.tests_team_season_tables import team_players  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


def listing(client, **params):
    return client.get(reverse("api_v1:teams"), params)


def detail(client, nhl_id=7, **params):
    return client.get(reverse("api_v1:team-detail", kwargs={"nhl_id": nhl_id}), params)


def players(client, nhl_id=7, **params):
    return client.get(reverse("api_v1:team-players", kwargs={"nhl_id": nhl_id}), params)


def result(client, nhl_id=7, **params):
    response = players(client, nhl_id, **params)
    assert response.status_code == 200, response.content
    return response.json()


def test_team_list_is_public_current_metadata_without_inferred_active_membership(
    client, team_players
):
    team = team_players["BUF"]
    team.arena_name, team.arena_location = "Fixture Arena", "Fixture City"
    team.division, team.conference = "Atlantic", "Eastern"
    team.off_site, team.nhl_debut = "https://example.invalid/team", "1970"
    team.image = "teams_logos/fixture.svg"
    team.save()
    Team.objects.create(nhl_id=99, name="Historical Empty Team", abbr="OLD")
    response = listing(client)
    assert response.status_code == 200 and response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"]
    data = response.json()
    assert data["count"] == 3 and data["meta"] == {"ordering": "name,nhl_id"}
    row = data["results"][0]
    assert row == {
        "nhl_id": 7,
        "name": team.name,
        "abbr": "BUF",
        "slug": team.slug,
        "image_url": "/media/teams_logos/fixture.svg",
        "arena_name": "Fixture Arena",
        "arena_location": "Fixture City",
        "division": "Atlantic",
        "conference": "Eastern",
        "website_url": "https://example.invalid/team",
        "nhl_debut": "1970",
    }
    assert data["results"][-1]["image_url"] is None
    assert "active" not in row and "season_id" not in data["meta"]


def test_team_list_filters_ordering_and_pagination_are_global(client, team_players):
    Team.objects.filter(nhl_id=7).update(conference="Eastern", division="Atlantic")
    Team.objects.filter(nhl_id=16).update(conference="Western", division="Central")
    assert listing(client, search=" buf ").json()["count"] == 1
    assert listing(client, search="%BUF").json()["results"] == []
    assert (
        listing(client, conference="Eastern,Western", division="Central").json()["results"][0][
            "nhl_id"
        ]
        == 16
    )
    first = listing(client, ordering="-name", page_size=1).json()
    assert first["results"][0]["nhl_id"] == 16
    second = client.get(first["next"]).json()
    assert second["results"][0]["nhl_id"] == 7
    assert first["meta"] == second["meta"]
    assert listing(client, page_size=1, page=3).status_code == 404
    Team.objects.filter(nhl_id__in=[7, 16]).update(name="Same")
    assert [row["nhl_id"] for row in listing(client).json()["results"]] == [7, 16]


def test_empty_team_list_has_standard_empty_envelope(client):
    assert listing(client).json() == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
        "meta": {"ordering": "name,nhl_id"},
    }


def test_detail_resolves_global_season_and_links_to_the_same_contributions(client, team_players):
    data = detail(client).json()
    assert data["team"]["nhl_id"] == 7 and data["meta"] == {"season_id": "20262027"}
    link = urlparse(data["players_url"])
    assert link.path == reverse("api_v1:team-players", kwargs={"nhl_id": 7})
    assert parse_qs(link.query) == {"season_id": ["20262027"]}
    assert client.get(data["players_url"]).json()["count"] == 3
    historical = detail(client, season_id="20252026").json()
    assert historical["meta"]["season_id"] == "20252026"
    assert parse_qs(urlparse(historical["players_url"]).query) == {"season_id": ["20252026"]}


def test_known_empty_team_remains_available_without_seasons_or_roster(client):
    Team.objects.create(nhl_id=7, name="Empty", abbr="BUF")
    data = detail(client).json()
    assert data["meta"]["season_id"] is None
    assert data["players_url"] == reverse("api_v1:team-players", kwargs={"nhl_id": 7})
    assert result(client)["results"] == []
    explicit = detail(client, season_id="20302031").json()
    assert explicit["meta"]["season_id"] == "20302031"


def test_team_players_use_exact_splits_not_roster_snapshots_or_combined_rows(client, team_players):
    data = result(client)
    assert data["count"] == 3
    assert data["meta"] == {
        "season_id": "20262027",
        "player_type": "skater",
        "mode": "totals",
        "ordering": "-points,last_name,nhl_id",
        "team": {
            "nhl_id": 7,
            "abbr": "BUF",
            "name": "Buffalo Sabres",
            "slug": team_players["BUF"].slug,
        },
    }
    assert {row["name"] for row in data["results"]} == {
        "Traded Forward",
        "Season Defender",
        "Missing Fields",
    }
    traded = next(row for row in data["results"] if row["nhl_id"] == 2)
    assert traded["stats"]["games"] == 6 and traded["stats"]["goals"] == 3
    assert traded["teams"] == [data["meta"]["team"]]
    assert traded["jersey_number"] == 20
    col = next(row for row in result(client, 16)["results"] if row["nhl_id"] == 2)
    assert col["stats"]["games"] == 4 and col["stats"]["goals"] == 1
    catalogue = client.get(reverse("api_v1:players"), {"team": "BUF"}).json()["results"]
    total = next(row for row in catalogue if row["nhl_id"] == 2)
    assert total["stats"]["games"] == 10 and total["stats"]["goals"] == 4
    assert {team["abbr"] for team in total["teams"]} == {"BUF", "COL"}


def test_team_averages_use_split_games_and_share_units_null_and_zero_contracts(
    client, team_players
):
    data = result(client, mode="averages", search="Traded")
    stats = data["results"][0]["stats"]
    assert stats["kind"] == "skater_averages" and stats["games"] == 6 and stats["goals"] == 0.5
    assert type(stats["avg_toi_seconds"]) is int
    missing = result(client, search="Missing")["results"][0]
    assert missing["stats"]["hits"] is None and missing["availability"] == "partial"
    defender = result(client, search="Defender")["results"][0]
    assert defender["jersey_number"] == 10


def test_goalie_rates_use_the_exact_team_row_even_with_tot_and_other_splits(client, team_players):
    buf = next(
        row for row in result(client, player_type="goalie")["results"] if row["nhl_id"] == 10
    )
    col = result(client, 16, player_type="goalie")["results"][0]
    assert buf["stats"]["kind"] == "goalie_totals"
    assert (buf["stats"]["games"], buf["stats"]["wins"], buf["stats"]["save_percentage"]) == (
        4,
        2,
        0.9,
    )
    assert (col["stats"]["games"], col["stats"]["wins"], col["stats"]["save_percentage"]) == (
        2,
        1,
        0.8,
    )
    assert col["stats"]["goals_against_average"] == 5.0
    missing = next(
        row for row in result(client, player_type="goalie")["results"] if row["nhl_id"] == 11
    )
    assert missing["stats"]["wins"] == 0 and missing["stats"]["save_percentage"] is None


def test_historical_and_empty_seasons_do_not_fall_back(client, team_players):
    old = result(client, season_id="20252026")
    assert any(row["nhl_id"] == team_players["historical"].nhl_id for row in old["results"])
    empty = result(client, season_id="20302031")
    assert (
        empty["count"] == 0 and empty["results"] == [] and empty["meta"]["season_id"] == "20302031"
    )
    assert players(client, season_id="20302031", page=2).status_code == 404


def test_default_is_global_not_latest_season_for_requested_team(client, team_players):
    Team.objects.create(nhl_id=99, name="Old Only", abbr="OLD")
    Skater.objects.create(
        nhl_id=99,
        name="Old Player",
        birth_date="2000-01-01",
        games=999,
        sbs_stats=[{"season": "2025-26", "teamAbbr": "OLD", "gamesPlayed": 1}],
    )
    assert detail(client, 99).json()["meta"]["season_id"] == "20262027"
    assert result(client, 99)["count"] == 0
    assert result(client, 99, season_id="20252026")["count"] == 1


@pytest.mark.parametrize(
    "params,ids",
    [
        ({"position": "D"}, [1]),
        ({"position": "C,LW"}, [2, 3]),
        ({"goals_min": 3}, [2]),
        ({"goals_max": 1}, [3]),
        ({"mode": "averages", "goals_min": 0.4}, [2]),
        ({"hits_isnull": "true"}, [3]),
        ({"search": "Defender"}, [1]),
    ],
)
def test_catalogue_filters_run_on_team_contributions_before_pagination(
    client, team_players, params, ids
):
    data = result(client, **params, page_size=1)
    assert data["count"] == len(ids)
    assert data["results"][0]["nhl_id"] == ids[0]


def test_team_pagination_ordering_nulls_and_implicit_identity_ties(client, team_players):
    first = result(client, page_size=1, ordering="-goals")
    second = client.get(first["next"]).json()
    assert first["results"][0]["nhl_id"] == 2 and second["results"][0]["nhl_id"] == 1
    assert first["meta"] == second["meta"]
    assert players(client, page_size=1, page=4).status_code == 404
    for order in ("hits", "-hits"):
        assert result(client, ordering=order)["results"][-1]["nhl_id"] == 3


@pytest.mark.parametrize("damage", ["duplicate", "malformed", "wrong_type", "wrong_league"])
def test_invalid_or_nonregular_team_rows_do_not_fall_back_to_combined_totals(
    client, team_players, damage
):
    traded = team_players["traded"]
    rows = deepcopy(traded.sbs_stats)
    if damage == "duplicate":
        rows.append(deepcopy(next(row for row in rows if row["teamAbbr"] == "BUF")))
    elif damage == "malformed":
        rows.append(None)
    else:
        for row in rows:
            if row["teamAbbr"] == "BUF":
                row["gameTypeId" if damage == "wrong_type" else "leagueAbbrev"] = (
                    3 if damage == "wrong_type" else "AHL"
                )
    Skater.objects.filter(pk=traded.pk).update(sbs_stats=rows)
    assert 2 not in {row["nhl_id"] for row in result(client)["results"]}


@pytest.mark.parametrize("abbr", ["", "TOT", "2TM"])
def test_saved_unusable_team_abbreviations_have_empty_contributions_not_invented_splits(
    client, team_players, abbr
):
    Team.objects.filter(nhl_id=7).update(abbr=abbr)
    assert detail(client).status_code == 200
    assert result(client)["results"] == []


@pytest.mark.parametrize(
    "route,query",
    [
        ("teams", {"season_id": "20262027"}),
        ("teams", {"ordering": "players"}),
        ("teams", {"ordering": "name,-name"}),
        ("teams", {"search": ""}),
        ("teams", {"conference": "Eastern,,Western"}),
        ("teams", {"page_size": 101}),
        ("team-detail", {"season_id": "2026-27"}),
        ("team-detail", {"season_id": "20262028"}),
        ("team-detail", {"season_id": ""}),
        ("team-detail", {"mode": "totals"}),
        ("team-players", {"team": "COL"}),
        ("team-players", {"mode": ""}),
        ("team-players", {"player_type": "all"}),
        ("team-players", {"wins_min": 1}),
        ("team-players", {"player_type": "goalie", "mode": "averages"}),
        ("team-players", {"goals_min": "NaN"}),
        ("team-players", {"page": 0}),
    ],
)
def test_bad_queries_return_typed_400_before_any_lookup(
    client, route, query, django_assert_num_queries
):
    url = reverse("api_v1:" + route, kwargs={"nhl_id": 7} if route != "teams" else None)
    with django_assert_num_queries(0):
        response = client.get(url, query)
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"


@pytest.mark.parametrize("route", ["teams", "team-detail", "team-players"])
def test_duplicate_parameters_rejected_before_lookup(client, route, django_assert_num_queries):
    url = reverse("api_v1:" + route, kwargs={"nhl_id": 7} if route != "teams" else None)
    with django_assert_num_queries(0):
        response = client.get(url + "?season_id=20262027&season_id=20252026")
    assert response.status_code == 400


@pytest.mark.parametrize("nhl_id", [0, 123456, 2**31, 10**30])
@pytest.mark.parametrize("route", ["team-detail", "team-players"])
def test_missing_or_unsafe_ids_are_json_404(client, nhl_id, route):
    response = client.get(reverse("api_v1:" + route, kwargs={"nhl_id": nhl_id}))
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


def test_bounded_read_only_queries_and_public_private_state_separation(
    client, team_players, offline, django_assert_num_queries
):
    before = {
        model: list(model.objects.order_by("pk").values()) for model in (Team, Skater, Goalie)
    }

    def select_only(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith(("SELECT", "DECLARE"))
        for token in (
            "advisory",
            "for update",
            "career_stats",
            "gamelog_stats",
            "sbs_stats_avg",
            "favoriting",
            "comparing",
        ):
            assert token not in sql.lower()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(select_only):
        with django_assert_num_queries(1):
            public_list = listing(client).json()
        with django_assert_num_queries(1):
            explicit_detail = detail(client, season_id="20262027").json()
        with django_assert_num_queries(2):
            public_players = result(client, season_id="20262027")
        with django_assert_num_queries(3):
            public_detail = detail(client).json()
        with django_assert_num_queries(4):
            result(client)
    assert before == {
        model: list(model.objects.order_by("pk").values()) for model in (Team, Skater, Goalie)
    }
    user = get_user_model().objects.create_user(username="private-team-viewer")
    user.favorite_skaters.add(team_players["traded"])
    user.comparable_goalies.add(team_players["goalie"])
    client.force_login(user)
    assert listing(client).json() == public_list
    assert detail(client).json() == public_detail
    assert detail(client, season_id="20262027").json() == explicit_detail
    assert result(client, season_id="20262027") == public_players
    assert not offline.called


@pytest.mark.parametrize("route", ["teams", "team-detail", "team-players"])
def test_methods_content_negotiation_and_no_store(client, team_players, route):
    url = reverse("api_v1:" + route, kwargs={"nhl_id": 7} if route != "teams" else None)
    response = client.head(url)
    assert response.status_code == 200 and response.content == b""
    assert "no-store" in response["Cache-Control"]
    assert client.post(url, {}, content_type="application/json").status_code == 405
    assert client.get(url, HTTP_ACCEPT="text/html").status_code == 406


def test_schema_has_public_team_routes_and_shared_typed_player_statistics(client):
    schema = client.get(reverse("api_v1:schema")).json()
    for path in ("/api/v1/teams/", "/api/v1/teams/{nhl_id}/", "/api/v1/teams/{nhl_id}/players/"):
        operation = schema["paths"][path]["get"]
        assert operation.get("security", []) in ([], [{}])
        assert {"200", "400", "404", "405", "406", "500"} <= operation["responses"].keys()
    params = schema["paths"]["/api/v1/teams/{nhl_id}/players/"]["get"]["parameters"]
    names = {parameter["name"] for parameter in params}
    assert (
        "team" not in names
        and {"season_id", "player_type", "mode", "position", "hits_isnull"} <= names
    )
    assert schema["components"]["schemas"]["TeamPlayer"]["properties"]["jersey_number"]["nullable"]
    assert (
        schema["components"]["schemas"]["CatalogueSeasonStatistics"]["discriminator"][
            "propertyName"
        ]
        == "kind"
    )


def test_team_player_queries_stay_bounded_and_serialize_only_the_requested_page(
    client, team_players, django_assert_num_queries, monkeypatch
):
    source = team_players["defender"]
    for index in range(100, 155):
        Skater.objects.create(
            nhl_id=index,
            name=f"Team Fixture {index}",
            last_name="Fixture",
            birth_date="2000-01-01",
            games=999,
            sbs_stats=source.sbs_stats,
            pl_number=12,
        )
    from players.api.team_serializers import TeamPlayerSerializer

    calls = []
    original = TeamPlayerSerializer.get_image_url

    def image_url(self, row):
        calls.append(row["nhl_id"])
        return original(self, row)

    monkeypatch.setattr(TeamPlayerSerializer, "get_image_url", image_url)
    with django_assert_num_queries(2):
        data = result(client, season_id="20262027")
    assert data["count"] == 58 and len(data["results"]) == len(calls) == 50
    assert len(result(client, season_id="20262027", page_size=100)["results"]) == 58
    assert all(row["jersey_number"] == 12 for row in data["results"] if row["nhl_id"] >= 100)


def test_team_list_page_sizes_are_bounded_without_per_team_queries(
    client, team_players, django_assert_num_queries
):
    for index in range(100, 151):
        Team.objects.create(nhl_id=index, name=f"Saved Team {index}", abbr=f"T{index}")
    with django_assert_num_queries(1):
        data = listing(client).json()
    assert data["count"] == 53 and len(data["results"]) == 50 and data["next"]
    with django_assert_num_queries(1):
        largest = listing(client, page_size=100).json()
    assert len(largest["results"]) == 53 and largest["next"] is None
