"""Loaded season discovery over synthetic persisted SBS rows only."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
import pytest

from players.models import Goalie, Skater
from players.player_table import available_seasons, selected_season

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def seasons():
    Skater.objects.create(
        birth_date="2000-01-01",
        games=999,
        nhl_id=1,
        name="Season Skater",
        stats_season_id="20992100",
        goals=999,
        sbs_stats=[
            {"season": "2025-26"},
            {"season": 20262027},
            {"season": "20262027", "teamAbbr": "TOT"},
            {"season": "20272028", "leagueAbbrev": "AHL"},
            {"season": "20282029", "gameTypeId": 3},
            {"season": "20292030", "gameTypeId": 1},
            {"season": "20262028"},
            {"season": "invalid"},
            {},
            None,
        ],
        sbs_stats_avg=[{"season": "2030-31"}],
    )
    Goalie.objects.create(
        birth_date="2000-01-01",
        games=999,
        nhl_id=2,
        name="Season Goalie",
        sbs_stats=[
            {"season": "2024-25", "leagueAbbrev": "NHL", "gameTypeId": 2},
            {"season": "2025-26"},
        ],
    )
    Skater.objects.create(
        birth_date="2000-01-01",
        games=999,
        nhl_id=3,
        name="Malformed",
        sbs_stats={"season": "20312032"},
    )
    Goalie.objects.create(birth_date="2000-01-01", games=999, nhl_id=4, name="Empty", sbs_stats=[])


def get(client, query=""):
    return client.get(reverse("api_v1:seasons") + query)


def test_loaded_seasons_are_normalized_distinct_descending_and_share_legacy_default(
    client, seasons
):
    response = get(client)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"]
    assert response.json() == {
        "count": 3,
        "next": None,
        "previous": None,
        "results": [
            {"season_id": "20262027", "label": "2026-27"},
            {"season_id": "20252026", "label": "2025-26"},
            {"season_id": "20242025", "label": "2024-25"},
        ],
        "meta": {"default_season_id": selected_season(None)},
    }
    assert available_seasons() == ["20262027", "20252026", "20242025"]


def test_empty_database_has_no_calendar_fallback(client):
    assert get(client).json() == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
        "meta": {"default_season_id": None},
    }
    assert get(client, "?page=2").status_code == 404


def test_goalie_only_season_can_be_default_and_zero_games_still_establishes_loaded_row(client):
    Goalie.objects.create(
        birth_date="2000-01-01",
        games=999,
        nhl_id=5,
        name="Goalie",
        sbs_stats=[{"season": "2026-27", "gamesPlayed": 0}],
    )
    data = get(client).json()
    assert data["meta"]["default_season_id"] == "20262027"
    assert data["count"] == 1


def test_pagination_preserves_global_default(client, seasons):
    first = get(client, "?page_size=1").json()
    second = client.get(first["next"]).json()
    assert second["results"] == [{"season_id": "20252026", "label": "2025-26"}]
    assert second["meta"] == first["meta"] == {"default_season_id": "20262027"}
    assert second["count"] == 3 and second["previous"]
    assert get(client, "?page=4&page_size=1").status_code == 404


@pytest.mark.parametrize(
    "query",
    [
        "?season_id=20262027",
        "?page=0",
        "?page=1.0",
        "?page_size=101",
        "?page_size=-1",
        "?page=1&page=2",
        "?page_size=",
        "?ordering=season_id",
    ],
)
def test_invalid_queries_fail_before_database_access(client, query, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = get(client, query)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameters"


def test_read_only_bounded_queries_and_no_upstream_or_private_data(
    client, seasons, offline, django_assert_num_queries
):
    before = {model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie)}

    def select_only(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith(("SELECT", "DECLARE"))
        assert "for update" not in sql.lower() and "advisory" not in sql.lower()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(select_only), django_assert_num_queries(2):
        public = get(client).json()
    assert before == {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie)
    }
    user = get_user_model().objects.create_user(username="season-viewer")
    client.force_login(user)
    assert get(client).json() == public
    assert not offline.called


def test_methods_and_json_errors(client):
    assert client.head(reverse("api_v1:seasons")).content == b""
    response = client.post(reverse("api_v1:seasons"), {}, content_type="application/json")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert client.get(reverse("api_v1:seasons"), HTTP_ACCEPT="text/html").status_code == 406


def test_schema_documents_pagination_null_default_and_public_access(client):
    schema = client.get(reverse("api_v1:schema")).json()
    operation = schema["paths"]["/api/v1/seasons/"]["get"]
    assert operation["operationId"] == "seasons_list"
    assert operation.get("security", []) in ([], [{}])
    assert {param["name"] for param in operation["parameters"]} == {"page", "page_size"}
    assert schema["components"]["schemas"]["SeasonsMeta"]["properties"]["default_season_id"][
        "nullable"
    ]


def test_default_and_maximum_page_sizes(client):
    Skater.objects.create(
        nhl_id=10,
        name="Historical Seasons",
        birth_date="2000-01-01",
        games=0,
        sbs_stats=[{"season": f"{year}{year + 1}"} for year in range(1900, 2001)],
    )
    first = get(client).json()
    assert first["count"] == 101 and len(first["results"]) == 50
    assert first["next"] and first["previous"] is None
    largest = get(client, "?page_size=100").json()
    assert len(largest["results"]) == 100 and largest["next"]
    assert largest["meta"] == first["meta"] == {"default_season_id": "20002001"}
