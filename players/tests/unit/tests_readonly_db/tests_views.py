"""View integration contracts using explicit, rolled-back PostgreSQL fixtures."""

import pytest
from django.urls import reverse

from players.models import Note, Position

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def signed_in(client, view_data):
    client.force_login(view_data["user"])
    return client


@pytest.mark.parametrize(
    "route",
    ["about", "home", "players", "favorites", "teams", "auth_callback", "comparison"],
)
def test_authenticated_pages_render(route, signed_in, view_data):
    response = signed_in.get(reverse(route))
    assert response.status_code == 200
    assert response.wsgi_request.user.pk == view_data["user"].pk
    assert response.templates


def test_search_returns_only_matching_fixture_records(signed_in, view_data):
    player = view_data["skater"]
    response = signed_in.get(reverse("search"), {"q": player.name})
    assert response.status_code == 200
    assert response.context["players"] == [player]
    assert player.name.encode() in response.content


def test_search_without_query_requests_a_search_term(signed_in):
    response = signed_in.get(reverse("search"))
    assert response.status_code == 200
    assert response.content == b"Please submit a search term."


@pytest.mark.parametrize("route", ["player_detail", "player_gamelog"])
@pytest.mark.parametrize("key", ["skater", "goalie"])
def test_player_pages_render_requested_fixture(route, key, signed_in, view_data):
    player = view_data[key]
    response = signed_in.get(reverse(route, args=[player.slug, player.nhl_id]))
    assert response.status_code == 200
    assert response.context["player"].pk == player.pk
    assert player.name.encode() in response.content
    if route == "player_gamelog":
        assert len(response.context["gamelog"]) == 1


def test_team_and_game_pages_use_fixture_relationships(signed_in, view_data):
    team = view_data["home"]
    response = signed_in.get(reverse("team_detail", args=[team.slug, team.nhl_id]))
    assert response.status_code == 200
    assert team.name.encode() in response.content
    game = view_data["game"]
    response = signed_in.get(reverse("game_detail", args=[game.slug, game.nhl_id]))
    assert response.status_code == 200
    assert response.context["game"].pk == game.pk
    assert view_data["skater"].name.encode() in response.content


@pytest.mark.parametrize("requested", ["2026-10-01", "2000-01-01"])
def test_games_selects_loaded_day_or_latest_fallback(requested, signed_in, view_data):
    response = signed_in.get(reverse("games", args=[requested]))
    assert response.status_code == 200
    assert response.context["today"] == view_data["day"]
    assert view_data["game"].result.encode() in response.content


@pytest.mark.parametrize("mode", ["avg", "tot"])
@pytest.mark.parametrize("position", ["t", "d", "f"])
def test_team_ajax_modes_render(signed_in, view_data, mode, position):
    team = view_data["home"]
    response = signed_in.get(
        reverse("ajax_stats_switcher", args=[team.slug, team.nhl_id, mode, position]),
        {"season": "20262027"},
    )
    assert response.status_code == 200
    assert response.json()["season_id"] == "20262027"
    assert response.json()["stat_type"] == mode


@pytest.mark.parametrize(
    "kind,mode",
    [
        ("skaters", "season_tot"),
        ("skaters", "season_avg"),
        ("skaters", "career_tot"),
        ("skaters", "career_avg"),
        ("goalies", "season_tot"),
        ("goalies", "career_tot"),
    ],
)
def test_comparison_ajax_modes_render(signed_in, view_data, kind, mode):
    response = signed_in.get(reverse("ajax_comparison_stat_switcher", args=[kind, mode]))
    assert response.status_code == 200
    key = "skater" if kind == "skaters" else "goalie"
    assert view_data[key].name in response.json()["table"]


@pytest.mark.parametrize("key", ["skater", "goalie"])
@pytest.mark.parametrize(
    "route,relation", [("player_favorite", "favoriting"), ("player_compare", "comparing")]
)
def test_saved_actions_toggle_only_authenticated_user(signed_in, view_data, key, route, relation):
    player = view_data[key]
    user = view_data["user"]
    url = reverse(route, args=[player.slug, player.nhl_id])
    for expected in (False, True):
        response = signed_in.get(url)
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert getattr(player, relation).filter(pk=user.pk).exists() is expected


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
def test_reset_clears_only_requested_comparison_group(signed_in, view_data, kind):
    response = signed_in.get(reverse("reset_comparison", args=[kind]))
    assert response.status_code == 200
    user = view_data["user"]
    assert getattr(user, "comparable_" + kind).count() == 0
    other = "goalies" if kind == "skaters" else "skaters"
    assert getattr(user, "comparable_" + other).count() == 1
    assert user.favorite_skaters.count() == user.favorite_goalies.count() == 1


@pytest.mark.parametrize("key", ["skater", "goalie"])
@pytest.mark.parametrize("route", ["player_note", "player_positions"])
def test_edit_form_get_does_not_create_records(signed_in, view_data, key, route):
    player = view_data[key]
    response = signed_in.get(reverse(route, args=[player.slug, player.nhl_id]))
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert Note.objects.count() == Position.objects.count() == 0


@pytest.mark.parametrize("mode", ["tot", "avg", "gls"])
@pytest.mark.parametrize("favorites", [False, True])
def test_player_table_ajax_returns_only_selected_saved_players(
    signed_in, view_data, mode, favorites
):
    args = [mode, "page=1", "size=25", "col", "fcol", "rookie_filter=", "checkbox_filter="]
    if favorites:
        args.append("fav_filt=True")
    response = signed_in.get(reverse("ajax_players", args=args), {"season": "20262027"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == (2 if mode == "gls" and not favorites else 1)
    assert data["season_id"] == "20262027"


@pytest.mark.parametrize("kind,key", [("skt_log", "skater"), ("gls_log", "goalie")])
@pytest.mark.parametrize("size", ["size=25", "size=100"])
def test_favorites_gamelog_returns_fixture_only(signed_in, view_data, kind, key, size):
    response = signed_in.get(
        reverse("ajax_fav_players_gamelog", args=[kind, "page=1", size, "col", "fcol"])
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert view_data[key].name in response.json()["rows"][0][0]


@pytest.mark.parametrize(
    "route,args",
    [
        ("ajax_comparison_stat_switcher", ["skaters", "season_tot"]),
        ("reset_comparison", ["goalies"]),
        ("ajax_fav_players_gamelog", ["skt_log", "page=1", "size=25", "col", "fcol"]),
        (
            "ajax_players",
            [
                "tot",
                "page=1",
                "size=25",
                "col",
                "fcol",
                "rookie_filter=",
                "checkbox_filter=",
                "fav_filt=True",
            ],
        ),
    ],
)
def test_anonymous_private_ajax_is_forbidden(client, view_data, route, args):
    response = client.get(reverse(route, args=args))
    assert response.status_code == 403
    assert response.json()["authenticated"] is False
    assert view_data["user"].comparable_goalies.count() == 1


@pytest.mark.parametrize(
    "route", ["player_favorite", "player_compare", "player_note", "player_positions"]
)
def test_anonymous_player_actions_do_not_change_memberships(client, view_data, route):
    player = view_data["skater"]
    response = client.get(reverse(route, args=[player.slug, player.nhl_id]))
    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert player.favoriting.count() == player.comparing.count() == 1
    assert Note.objects.count() == Position.objects.count() == 0
