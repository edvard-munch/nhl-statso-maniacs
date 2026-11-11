"""Public identity search and bounded autocomplete without private data or HTML."""

from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.urls import reverse
import pytest

from players.models import Goalie, Note, Position, Skater, Team
from players.api.search import ENTITY_MODELS

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def entities():
    common = {
        "pk": 42,
        "nhl_id": 7,
        "birth_date": "2000-01-01",
        "games": 0,
        "sbs_stats": [],
        "career_stats": {},
    }
    skater = Skater.objects.create(
        name="Needle", position_abbr="C", image="players_pics/skater.png", **common
    )
    goalie = Goalie.objects.create(
        name="Needle Goalie", position_abbr="G", image="players_pics/goalie.png", **common
    )
    team = Team.objects.create(
        pk=42, nhl_id=7, name="Needle Team", abbr="NDL", image="teams_logos/team.png"
    )
    substring = Skater.objects.create(
        pk=43,
        nhl_id=8,
        name="A Needle",
        birth_date="1990-01-01",
        games=999,
        goals=999,
        sbs_stats=None,
        career_stats={},
    )
    other_goalie = Goalie.objects.create(
        pk=43,
        nhl_id=8,
        name="Z Needle",
        birth_date="1990-01-01",
        games=999,
        sbs_stats=None,
        career_stats={},
    )
    abbreviation = Team.objects.create(pk=43, nhl_id=8, name="Other Club", abbr="NEEDLE", image="")
    return {
        "skater": skater,
        "goalie": goalie,
        "team": team,
        "substring": substring,
        "other_goalie": other_goalie,
        "abbreviation": abbreviation,
    }


def get(client, suggestions=False, **params):
    return client.get(
        reverse("api_v1:search-suggestions" if suggestions else "api_v1:search"), params
    )


def identity(row):
    return row["entity_type"], row["nhl_id"]


def test_literal_matching_typed_identity_and_explicit_dto(client, entities):
    response = get(client, q="  NeEdLe  ")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 6
    assert data["meta"] == {
        "q": "NeEdLe",
        "entity_types": ["skater", "goalie", "team"],
        "ordering": "relevance,name,entity_type,nhl_id",
    }
    assert len({identity(row) for row in data["results"]}) == 6
    typed = {row["entity_type"]: row for row in data["results"] if row["nhl_id"] == 7}
    assert typed.keys() == {"skater", "goalie", "team"}
    for row in data["results"]:
        assert set(row) == {
            "entity_type",
            "nhl_id",
            "name",
            "slug",
            "image_url",
            "position_abbr",
            "abbr",
        }
        assert not {
            "id",
            "pk",
            "stats",
            "availability",
            "favoriting",
            "comparing",
            "note",
            "positions",
        }.intersection(row)
    assert typed["skater"]["position_abbr"] == "C" and typed["skater"]["abbr"] is None
    assert typed["goalie"]["position_abbr"] == "G" and typed["team"]["position_abbr"] is None
    assert typed["team"]["abbr"] == "NDL"
    for kind, row in typed.items():
        assert row["slug"] == entities[kind].slug and row["image_url"] == entities[kind].image.url
        target = (
            reverse("api_v1:team-detail", args=[row["nhl_id"]])
            if kind == "team"
            else reverse("api_v1:player-detail", args=[kind, row["nhl_id"]])
        )
        assert client.get(target).status_code == 200
    assert next(row for row in data["results"] if identity(row) == ("team", 8))["image_url"] is None


def test_relevance_is_exact_then_prefix_then_substring_and_global_pages_are_stable(
    client, entities
):
    data = get(client, q="needle", page_size=2).json()
    first = [identity(row) for row in data["results"]]
    assert first == [("skater", 7), ("team", 8)]
    second = client.get(data["next"]).json()
    third = client.get(second["next"]).json()
    assert [identity(row) for row in second["results"]] == [("goalie", 7), ("team", 7)]
    assert [identity(row) for row in third["results"]] == [("skater", 8), ("goalie", 8)]
    assert third["next"] is None
    assert client.get(second["previous"]).json() == data
    assert get(client, q="needle", page_size=2, page=4).status_code == 404


@pytest.mark.parametrize(
    "params,expected",
    [
        ({"entity_type": "skater"}, {("skater", 7), ("skater", 8)}),
        ({"entity_type": "goalie"}, {("goalie", 7), ("goalie", 8)}),
        ({"entity_type": "team"}, {("team", 7), ("team", 8)}),
        ({"entity_type": "team,goalie"}, {("team", 7), ("team", 8), ("goalie", 7), ("goalie", 8)}),
    ],
)
def test_entity_filters_apply_before_count_pagination_and_preview(
    client, entities, params, expected
):
    data = get(client, q="needle", **params).json()
    assert {identity(row) for row in data["results"]} == expected and data["count"] == len(expected)
    preview = get(client, True, q="needle", limit=20, **params).json()
    assert preview["results"] == data["results"]
    assert preview["meta"]["entity_types"] == data["meta"]["entity_types"]
    assert not preview["meta"]["has_more"]
    if "goalie" in params["entity_type"] and "team" in params["entity_type"]:
        assert data["meta"]["entity_types"] == ["goalie", "team"]


@pytest.mark.parametrize("q", [None, "", "   ", "\t\n"])
@pytest.mark.parametrize("suggestions", [True, False])
def test_blank_queries_have_empty_shape_and_no_database_access(
    client, entities, q, suggestions, django_assert_num_queries
):
    params = {} if q is None else {"q": q}
    with django_assert_num_queries(0):
        response = get(client, suggestions, **params)
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == [] and data["meta"]["q"] == ""
    if suggestions:
        assert not data["meta"]["has_more"]
    else:
        assert data["count"] == 0 and data["next"] is None and data["previous"] is None
        with django_assert_num_queries(0):
            assert get(client, page=2, **params).status_code == 404


def test_suggestions_are_bounded_have_more_signal_and_use_one_query_without_count(
    client, entities, django_assert_num_queries
):
    with django_assert_num_queries(1):
        data = get(client, True, q="needle", limit=3).json()
    assert len(data["results"]) == 3 and data["meta"]["has_more"]
    assert data["meta"]["limit"] == 3
    assert data["results"] == get(client, q="needle").json()["results"][:3]
    exact = get(client, True, q="needle", limit=6).json()
    assert len(exact["results"]) == 6 and not exact["meta"]["has_more"]
    assert get(client, True, q="needle").json()["meta"]["limit"] == 10


@pytest.mark.parametrize("suggestions", [True, False])
def test_no_matches_are_empty_with_bounded_database_queries(
    client, entities, suggestions, django_assert_num_queries
):
    with django_assert_num_queries(1):
        data = get(client, suggestions, q="no-matching-fixture").json()
    assert data["results"] == []
    if suggestions:
        assert not data["meta"]["has_more"]
    else:
        assert data["count"] == 0


@pytest.mark.parametrize(
    "q", ["%", "_", "Émile", 'A&B # + ? "', "<img src=x onerror=alert(1)>", "' OR 1=1 --"]
)
def test_terms_are_literal_data_and_navigation_query_is_encoded(client, entities, q):
    player = entities["skater"]
    player.name = q + " Fixture"
    player.save(update_fields=["name"])
    data = get(client, q=q, page_size=1).json()
    assert data["count"] == 1 and data["results"][0]["name"] == q + " Fixture"
    assert get(client, True, q=q).json()["results"] == data["results"]
    second = Goalie.objects.create(
        pk=44, nhl_id=99, name=q + " Other", birth_date="2000-01-01", games=0, sbs_stats=[]
    )
    data = get(client, q=q, page_size=1).json()
    parsed = urlsplit(data["next"])
    assert parsed.fragment == "" and parse_qs(parsed.query)["q"] == [q]
    assert client.get(data["next"]).json()["results"][0]["nhl_id"] == second.nhl_id


def test_name_case_matching_and_team_abbreviation_substrings_are_supported(client, entities):
    row = entities["goalie"]
    row.name = "Émile Fixture"
    row.save(update_fields=["name"])
    assert get(client, q="éMILE").json()["results"][0]["nhl_id"] == row.nhl_id
    assert get(client, q="ndl").json()["results"][0]["entity_type"] == "team"
    assert get(client, q="ND").json()["results"][0]["abbr"] == "NDL"
    assert get(client, q="emiLe").json()["count"] == 0  # No invented accent folding.


def test_rank_ties_use_type_and_nhl_id_without_collapsing_models(client, entities):
    for model in (Skater, Goalie, Team):
        model.objects.all().update(name="Same Name", image="")
    rows = get(client, q="Same Name").json()["results"]
    assert [identity(row) for row in rows] == [
        ("skater", 7),
        ("skater", 8),
        ("goalie", 7),
        ("goalie", 8),
        ("team", 7),
        ("team", 8),
    ]


def test_read_queries_fetch_only_identity_columns_and_do_not_depend_on_seasons_or_history(
    client, entities, django_assert_num_queries, offline
):
    before = {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie, Team)
    }

    def read_only(execute, sql, params, many, context):
        assert sql.lstrip(" (\n\t").upper().startswith("SELECT")
        assert not any(
            field in sql.lower()
            for field in (
                "sbs_stats",
                "career_stats",
                "gamelog_stats",
                "stats_season_id",
                '"games"',
                "auth_user",
                "players_note",
                "players_position",
                "favoriting",
                "comparing",
            )
        )
        return execute(sql, params, many, context)

    with connection.execute_wrapper(read_only), django_assert_num_queries(2):
        assert get(client, q="needle").json()["count"] == 6
    with connection.execute_wrapper(read_only), django_assert_num_queries(1):
        assert len(get(client, True, q="needle").json()["results"]) == 6
    assert before == {
        model: list(model.objects.order_by("pk").values()) for model in (Skater, Goalie, Team)
    }
    assert not offline.called


def test_query_counts_and_limits_remain_bounded_with_large_mixed_results(
    client, entities, django_assert_num_queries
):
    for model in (Skater, Goalie):
        model.objects.bulk_create(
            [
                model(
                    pk=1000 + i,
                    nhl_id=1000 + i,
                    name=f"Bulk Match {i:03}",
                    slug=f"bulk-{i}",
                    birth_date="2000-01-01",
                    games=0,
                )
                for i in range(80)
            ]
        )
    Team.objects.bulk_create(
        [
            Team(
                pk=1000 + i,
                nhl_id=1000 + i,
                name=f"Bulk Match {i:03}",
                slug=f"bulk-{i}",
                abbr=f"B{i}",
            )
            for i in range(80)
        ]
    )
    captured = []

    def capture(execute, sql, params, many, context):
        captured.append(sql)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(capture), django_assert_num_queries(2):
        data = get(client, q="Bulk", page=4, page_size=50).json()
    assert data["count"] == 240 and len(data["results"]) == 50
    assert "LIMIT 50 OFFSET 150" in captured[-1]
    with connection.execute_wrapper(capture), django_assert_num_queries(1):
        preview = get(client, True, q="Bulk", limit=20).json()
    assert len(preview["results"]) == 20 and preview["meta"]["has_more"]
    assert "LIMIT 21" in captured[-1] and "COUNT(" not in captured[-1]


def test_public_results_are_identical_for_anonymous_and_both_saved_state_owners(
    client, entities, django_assert_num_queries
):
    anonymous = get(client, q="needle").json()
    preview = get(client, True, q="needle").json()
    for index in range(2):
        owner = get_user_model().objects.create_user(username=f"search-viewer-{index}")
        entities["skater"].favoriting.add(owner)
        entities["goalie"].comparing.add(owner)
        Note.objects.create(
            author=owner,
            content_object=entities["skater"],
            player_name=entities["skater"].name,
            text="private secret",
        )
        Position.objects.create(
            author=owner,
            content_object=entities["skater"],
            player_name=entities["skater"].name,
            data=["D"],
        )
        ContentType.objects.get_for_model(entities["skater"])
        client.force_login(owner)
        with django_assert_num_queries(2):
            assert get(client, q="needle").json() == anonymous
        with django_assert_num_queries(1):
            assert get(client, True, q="needle").json() == preview
    assert "private secret" not in str(anonymous)


def test_image_urls_use_correct_model_storage_without_reading_image_bytes(
    client, entities, monkeypatch
):
    def fail(*args, **kwargs):
        raise AssertionError("Search must not read or write storage")

    for kind, model in ENTITY_MODELS.items():
        storage = SimpleNamespace(
            open=fail,
            save=fail,
            exists=fail,
            url=lambda name, kind=kind: f"/search-images/{kind}/{name}",
        )
        monkeypatch.setattr(model._meta.get_field("image"), "storage", storage)
    data = get(client, q="needle").json()
    for row in data["results"]:
        if row["image_url"]:
            assert row["image_url"].startswith("/search-images/" + row["entity_type"] + "/")


@pytest.mark.parametrize(
    "params",
    [
        {"q": ["needle", "other"]},
        {"q": "x" * 129},
        {"q": "bad\u0000term"},
        {"entity_type": ""},
        {"entity_type": "player"},
        {"entity_type": "Skater"},
        {"entity_type": "skater,skater"},
        {"entity_type": "skater,"},
        {"entity_type": ["skater", "goalie"]},
        {"owner": "1"},
        {"season_id": "20262027"},
        {"ordering": "name__icontains"},
    ],
)
@pytest.mark.parametrize("suggestions", [True, False])
def test_invalid_queries_fail_before_any_database_access(
    client, entities, params, suggestions, django_assert_num_queries
):
    with django_assert_num_queries(0):
        response = get(client, suggestions, **params)
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"


@pytest.mark.parametrize(
    "params",
    [{"page": "0"}, {"page_size": "101"}, {"page": "1.5"}, {"limit": "1"}, {"page_size": ""}],
)
def test_search_rejects_invalid_pagination_and_preview_parameters(
    client, params, django_assert_num_queries
):
    with django_assert_num_queries(0):
        assert get(client, q="needle", **params).status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "21"},
        {"limit": ""},
        {"limit": "1.5"},
        {"page": "2"},
        {"page_size": "1"},
    ],
)
def test_preview_rejects_invalid_limits_and_page_parameters(
    client, params, django_assert_num_queries
):
    with django_assert_num_queries(0):
        assert get(client, True, q="needle", **params).status_code == 400


@pytest.mark.parametrize("suggestions", [True, False])
def test_only_get_head_are_supported_and_html_negotiation_is_not_accepted(
    client, entities, suggestions
):
    target = reverse("api_v1:search-suggestions" if suggestions else "api_v1:search")
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(target).status_code == 405
    response = client.get(target, {"q": "needle"}, HTTP_ACCEPT="text/html")
    assert response.status_code == 406 and response["Content-Type"] == "application/json"
    assert client.head(target, {"q": "needle"}).status_code == 200


def test_schema_has_public_identity_search_and_bounded_preview(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    for target in ("/api/v1/search/", "/api/v1/search/suggestions/"):
        operation = schema["paths"][target]["get"]
        assert operation.get("security", []) in ([], [{}])
    result = schema["components"]["schemas"]["SearchEntity"]["properties"]
    assert set(result) == {
        "entity_type",
        "nhl_id",
        "name",
        "slug",
        "image_url",
        "position_abbr",
        "abbr",
    }
    assert "SearchEntityTypeEnum" in schema["components"]["schemas"]
