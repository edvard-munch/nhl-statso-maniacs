"""Favorites-only player identity ordering is global, typed and owner scoped."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.urls import reverse
import pytest

from players.models import Goalie, Skater

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def favorite_rows(client):
    owner = get_user_model().objects.create_user(username="ordering-owner")
    other = get_user_model().objects.create_user(username="ordering-other")
    dates = ["2026-11-03", "2026-11-01", "2026-11-02"]
    players = [
        Skater.objects.create(
            nhl_id=nhl_id,
            name=name,
            last_name=last_name,
            games=0,
            birth_date="2000-01-01",
            position_abbr="C",
            gamelog_stats={day: {} for day in dates},
        )
        for nhl_id, name, last_name in [
            (100, "ZOË Alpha", "Alpha"),
            (2, "adam Zulu", "Zulu"),
            (30, "Béta Beta", "beta"),
        ]
    ]
    goalie = Goalie.objects.create(
        nhl_id=2,
        name="Same ID goalie",
        last_name="Goalie",
        games=0,
        birth_date="2000-01-01",
        position_abbr="G",
        gamelog_stats={day: {} for day in dates},
    )
    outsider = Skater.objects.create(
        nhl_id=900,
        name="AAA Other owner",
        last_name="Other",
        games=0,
        birth_date="2000-01-01",
        gamelog_stats={day: {} for day in dates},
    )
    owner.favorite_skaters.add(*players)
    owner.favorite_goalies.add(goalie)
    other.favorite_skaters.add(outsider)
    owner.comparable_skaters.add(outsider)
    client.force_login(owner)
    return SimpleNamespace(owner=owner, other=other, players=players, goalie=goalie, dates=dates)


def listing(client, **params):
    return client.get(reverse("api_v1:favorites-gamelog"), params)


def all_pages(client, **params):
    response = listing(client, **params)
    assert response.status_code == 200, response.content
    data = response.json()
    rows = data["results"]
    next_page = data["next"]
    while next_page:
        assert len(rows) < data["count"]
        response = client.get(next_page)
        assert response.status_code == 200, response.content
        page = response.json()
        assert page["meta"] == data["meta"]
        rows.extend(page["results"])
        next_page = page["next"]
    assert len(rows) == data["count"]
    return rows, data


@pytest.mark.parametrize(
    "ordering, identities",
    [
        ("player_name", [2, 30, 100]),
        ("-player_name", [100, 30, 2]),
        ("player_last_name", [100, 30, 2]),
        ("-player_last_name", [2, 30, 100]),
        ("player_nhl_id", [2, 30, 100]),
        ("-player_nhl_id", [100, 30, 2]),
    ],
)
def test_identity_ordering_precedes_paging_and_uses_nhl_identity_not_primary_key(
    client, favorite_rows, ordering, identities
):
    rows, data = all_pages(client, ordering=ordering, page_size=2)
    assert [row["player"]["nhl_id"] for row in rows] == [
        identity for identity in identities for _ in range(3)
    ]
    assert {row["player"]["player_type"] for row in rows} == {"skater"}
    assert data["count"] == 9 and data["meta"]["ordering"] == ordering
    assert data["meta"]["quota"]["total_count"] == 4
    assert all(row["game"] is None and row["availability"] == "unverified" for row in rows)
    assert all(all(value is None for value in row["stats"].values()) for row in rows)


@pytest.mark.parametrize(
    "field, attribute", [("player_name", "name"), ("player_last_name", "last_name")]
)
@pytest.mark.parametrize("blank", ["", "  "])
@pytest.mark.parametrize("direction", ["", "-"])
def test_blank_identity_names_sort_last_in_both_directions(
    client, favorite_rows, field, attribute, blank, direction
):
    missing = favorite_rows.players[2]
    Skater.objects.filter(pk=missing.pk).update(**{attribute: blank})
    rows, _ = all_pages(client, ordering=direction + field, page_size=2)
    assert [row["player"]["nhl_id"] for row in rows[-3:]] == [30, 30, 30]
    assert all(row["player"][attribute] == blank for row in rows[-3:])


def test_identity_and_descending_date_compound_keys_are_applied_left_to_right(
    client, favorite_rows
):
    for player in favorite_rows.players[:2]:
        Skater.objects.filter(pk=player.pk).update(last_name="Same")
    Skater.objects.filter(pk=favorite_rows.players[2].pk).update(last_name="ZZZ")
    rows, _ = all_pages(client, ordering="player_last_name,player_nhl_id,-date", page_size=2)
    assert [(row["player"]["nhl_id"], row["date"]) for row in rows] == [
        (identity, day)
        for identity in (2, 100, 30)
        for day in ("2026-11-03", "2026-11-02", "2026-11-01")
    ]


def test_equal_names_keep_existing_date_game_and_typed_identity_ties(client, favorite_rows):
    for player in favorite_rows.players:
        Skater.objects.filter(pk=player.pk).update(name="Same Name", last_name="Same")
    rows, _ = all_pages(client, ordering="player_name", page_size=1)
    assert [(row["date"], row["player"]["nhl_id"]) for row in rows] == [
        (day, identity)
        for day in ("2026-11-01", "2026-11-02", "2026-11-03")
        for identity in (2, 30, 100)
    ]


@pytest.mark.parametrize("ordering", ["player_name", "-player_last_name", "player_nhl_id"])
def test_goalie_identity_ordering_never_mixes_same_nhl_id_from_skaters(
    client, favorite_rows, ordering
):
    rows, data = all_pages(client, player_type="goalie", ordering=ordering, page_size=1)
    assert data["count"] == 3
    assert {(row["player"]["player_type"], row["player"]["nhl_id"]) for row in rows} == {
        ("goalie", 2)
    }
    assert {row["player"]["name"] for row in rows} == {"Same ID goalie"}


def test_existing_statistic_filters_and_unknown_sort_values_compose_with_identity_ordering(
    client, favorite_rows
):
    rows, _ = all_pages(
        client, ordering="goals,player_name,-date", goals_isnull="true", page_size=2
    )
    assert [(row["player"]["nhl_id"], row["date"]) for row in rows] == [
        (identity, day)
        for identity in (2, 30, 100)
        for day in ("2026-11-03", "2026-11-02", "2026-11-01")
    ]
    data = listing(client, ordering="player_name", goals_min=1).json()
    assert data["count"] == 0 and data["results"] == []
    assert data["meta"]["quota"]["total_count"] == 4


@pytest.mark.parametrize(
    "params",
    [
        {"ordering": "player_name,player_name"},
        {"ordering": "player_name,-player_name"},
        {"ordering": "player__name"},
        {"ordering": "player.name"},
        {"ordering": "player_name,"},
        {"ordering": "--player_nhl_id"},
        {"ordering": "player_type"},
        {"player_nhl_id_min": 2},
        {"player_type": "goalie", "ordering": "player_name,goals"},
        {"player_type": "skater", "ordering": "player_name,decision"},
        {"ordering": ["player_name", "player_nhl_id"]},
    ],
)
def test_ordering_allowlist_cannot_be_widened_by_paths_duplicates_or_wrong_types(
    client, favorite_rows, params
):
    before = list(
        favorite_rows.owner.favorite_skaters.order_by("nhl_id").values_list("nhl_id", flat=True)
    )
    response = listing(client, **params)
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "invalid_parameters"
    assert (
        list(
            favorite_rows.owner.favorite_skaters.order_by("nhl_id").values_list("nhl_id", flat=True)
        )
        == before
    )


@pytest.mark.parametrize("field", ["player_name", "player_last_name", "player_nhl_id"])
def test_public_single_player_gamelog_does_not_accept_favorites_only_keys(
    client, favorite_rows, field
):
    response = client.get(reverse("api_v1:player-gamelog", args=["skater", 2]), {"ordering": field})
    assert response.status_code == 400
    assert "ordering" in response.json()["error"]["fields"]


def test_schema_describes_private_keys_without_mutating_public_query_fields(client):
    schema = client.get(reverse("api_v1:schema")).json()
    private = schema["paths"]["/api/v1/me/favorites/gamelog/"]["get"]
    public = schema["paths"]["/api/v1/players/{player_type}/{nhl_id}/gamelog/"]["get"]
    private_order = next(field for field in private["parameters"] if field["name"] == "ordering")
    public_order = next(field for field in public["parameters"] if field["name"] == "ordering")
    for field in ("player_name", "player_last_name", "player_nhl_id"):
        assert field in private_order["description"]
        assert field not in public_order["description"]
    assert private_order["schema"]["default"] == public_order["schema"]["default"] == "-date"
    assert private["security"] == [{"cookieAuth": []}]


def test_unicode_casefold_equivalence_keeps_identity_ties_across_pages(client, favorite_rows):
    for player, name in zip(favorite_rows.players, ["Straße", "STRASSE", "ZZZ"]):
        Skater.objects.filter(pk=player.pk).update(name=name, last_name="Same")
    rows, _ = all_pages(client, ordering="player_name", page_size=2)
    assert [(row["player"]["nhl_id"], row["date"]) for row in rows] == [
        (identity, day)
        for day in ("2026-11-01", "2026-11-02", "2026-11-03")
        for identity in (2, 100)
    ] + [(30, day) for day in ("2026-11-01", "2026-11-02", "2026-11-03")]
