"""Filter metadata uses complete public season populations, never table pages."""

from copy import deepcopy

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
import pytest

from players.models import Skater, Team
from players.tests.integration.tests_players_api_db import catalogue_players  # noqa: F401
from players.tests.integration.tests_players_season_table import table_players  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


def get(client, **params):
    return client.get(reverse("api_v1:players-filters"), params)


def test_complete_population_ranges_and_options(client, catalogue_players):
    with CaptureQueriesContext(connection) as queries:
        response = get(client, season_id="20262027")
    assert response.status_code == 200, response.content
    assert len(queries) == 2
    assert all(item["sql"].lstrip().startswith(("SELECT", "DECLARE")) for item in queries)
    assert "no-store" in response["Cache-Control"]
    data = response.json()
    assert data["meta"] == {"season_id": "20262027", "player_type": "skater", "mode": "totals"}
    assert data["initial_count"] == data["options_count"] == data["filtered_count"] == 2
    assert data["initial_ranges"]["goals"] == {"min": 2, "max": 4}
    assert data["initial_ranges"]["age"] == {"min": 20, "max": 30}
    assert data["height_values_cm"] == [180, 190]
    assert data["options"]["nations"] == [
        {"code": "CAN", "label": "Canada"},
        {"code": "SWE", "label": "Sweden"},
    ]
    assert [row["code"] for row in data["options"]["positions"]] == ["C", "D"]
    assert data["filtered_ranges"] == data["initial_ranges"]
    assert set(data["options"]) == {"teams", "nations", "positions"}


def test_categorical_selections_do_not_shrink_options(client, catalogue_players):
    data = get(client, nation="CAN", position="D", team="COL").json()
    assert data["options_count"] == 2 and data["filtered_count"] == 1
    assert len(data["options"]["nations"]) == 2
    assert data["initial_ranges"]["goals"] == {"min": 2, "max": 4}
    assert data["filtered_ranges"]["goals"] == {"min": 2, "max": 2}
    assert data["height_values_cm"] == [180]


@pytest.mark.parametrize(
    "params",
    [
        {"search": "High"},
        {"age_min": "25"},
        {"birth_date_max": "1999-01-01"},
        {"goals_min": "3"},
        {"hits_isnull": "true"},
        {"rookie": "true"},
    ],
)
def test_noncategorical_filters_match_catalogue(client, catalogue_players, params):
    high = catalogue_players["high"]
    high.rookie = True
    high.save(update_fields=["rookie"])
    data = get(client, **params).json()
    catalogue = client.get(reverse("api_v1:players"), params).json()
    assert data["initial_count"] == 2
    assert data["options_count"] == data["filtered_count"] == catalogue["count"] == 1
    assert data["options"]["nations"] == [{"code": "SWE", "label": "Sweden"}]


def test_averages_goalies_and_empty_selected_season(client, catalogue_players):
    data = get(client, mode="averages", goals_min="0.5").json()
    assert data["initial_ranges"]["goals"] == {"min": 0.2, "max": 0.8}
    assert data["filtered_ranges"]["goals"] == {"min": 0.8, "max": 0.8}
    goalie = get(client, player_type="goalie").json()
    assert goalie["initial_count"] == 1
    assert "save_percentage" in goalie["initial_ranges"]
    assert "goals" not in goalie["initial_ranges"]
    data = get(client, season_id="20302031").json()
    assert data["meta"]["season_id"] == "20302031"
    assert data["initial_count"] == data["filtered_count"] == 0
    assert data["options"] == {"teams": [], "nations": [], "positions": []}
    assert all(bounds == {"min": None, "max": None} for bounds in data["initial_ranges"].values())


def test_no_loaded_seasons(client):
    data = get(client).json()
    assert data["meta"]["season_id"] is None
    assert data["initial_count"] == 0 and data["height_values_cm"] == []


def test_historical_team_fallback_and_zero_unknown_values(client, catalogue_players):
    low = catalogue_players["low"]
    low.sbs_stats = [{**row, "teamAbbr": "OLD", "goals": 0, "hits": None} for row in low.sbs_stats]
    low.height_cm = 0
    low.save(update_fields=["sbs_stats", "height_cm"])
    data = get(client, season_id="20262027", team="OLD").json()
    old = next(row for row in data["options"]["teams"] if row["abbr"] == "OLD")
    assert old == {"abbr": "OLD", "name": "OLD", "nhl_id": None, "slug": None}
    assert data["filtered_ranges"]["goals"] == {"min": 0, "max": 0}
    assert data["filtered_ranges"]["hits"] == {"min": None, "max": None}
    assert data["height_values_cm"] == [0]
    historical = get(client, season_id="20252026").json()
    assert historical["initial_count"] > 0


def test_metadata_includes_players_beyond_first_page(client, catalogue_players):
    source = catalogue_players["low"]
    Skater.objects.bulk_create(
        [
            Skater(
                nhl_id=1000 + index,
                name=f"Extra {index}",
                last_name="Extra",
                games=0,
                birth_date="2000-01-01",
                nation_abbr="NEW",
                nation="New country",
                sbs_stats=deepcopy(source.sbs_stats),
            )
            for index in range(101)
        ]
    )
    page = client.get(reverse("api_v1:players"), {"page_size": 1}).json()
    with CaptureQueriesContext(connection) as queries:
        data = get(client, season_id="20262027").json()
    assert len(queries) == 2
    assert data["initial_count"] == page["count"] == 103
    assert {item["code"] for item in data["options"]["nations"]} == {"CAN", "SWE", "NEW"}
    Team.objects.all().delete()
    assert get(client, season_id="20262027").status_code == 200


@pytest.mark.parametrize(
    "query",
    [
        "page=1",
        "page_size=10",
        "ordering=name",
        "season_id=2026",
        "mode=averages&player_type=goalie",
        "search=",
        "rookie=1",
        "age_min=nan",
        "age_min=30&age_max=20",
        "wins_min=1",
        "nation=CAN&nation=SWE",
        "unknown=1",
        "team=BUF,BUF",
    ],
)
def test_invalid_parameters_are_rejected_without_queries(client, django_assert_num_queries, query):
    with django_assert_num_queries(0):
        response = client.get(reverse("api_v1:players-filters") + "?" + query)
    assert response.status_code == 400
    assert response["Content-Type"] == "application/json"


def test_unknown_category_has_empty_filtered_ranges_and_method_is_read_only(
    client, catalogue_players
):
    data = get(client, nation="XXX").json()
    assert data["filtered_count"] == 0 and data["options_count"] == 2
    assert all(item == {"min": None, "max": None} for item in data["filtered_ranges"].values())
    assert client.post(reverse("api_v1:players-filters"), {}).status_code == 405


def test_traded_season_options_preserve_all_participation_and_empty_labels(
    client, catalogue_players
):
    low = catalogue_players["low"]
    current = next(row for row in low.sbs_stats if row["season"] == "2026-27")
    low.sbs_stats = [
        {**current, "teamAbbr": "TOT"},
        {**current, "teamAbbr": "OLD"},
        {**current, "teamAbbr": "COL"},
    ]
    low.nation = ""
    low.position_name = ""
    low.save(update_fields=["sbs_stats", "nation", "position_name"])
    data = get(client, search="Low", team="OLD").json()
    assert data["filtered_count"] == 1
    assert [team["abbr"] for team in data["options"]["teams"]] == ["COL", "OLD"]
    assert data["options"]["nations"] == [{"code": "CAN", "label": "CAN"}]
    assert data["options"]["positions"] == [{"code": "D", "label": "D"}]
