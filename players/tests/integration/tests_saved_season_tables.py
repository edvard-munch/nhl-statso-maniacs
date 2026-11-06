import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from players import saved_players
from players.models import Goalie
from players.tests.integration.tests_players_season_table import (
    ajax,
    names,
    stored_rows,
    table_players,
)  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def saved_user(client, table_players):
    user = User.objects.create_user(username="saved-seasons")
    user.favorite_skaters.add(*[table_players[key] for key in ("low", "old", "zero")])
    user.comparable_skaters.add(table_players["low"], table_players["old"])
    client.force_login(user)
    return user


def test_favorites_preserve_unavailable_and_zero_game_players(client, saved_user, table_players):
    data = ajax(client, favorites="favorites_filter=true").json()
    assert data["total"] == 3
    old_index = next(i for i, name in enumerate(names(data)) if "Historical Only" in name)
    assert "No statistics for 2026-27" in names(data)[old_index]
    assert data["rows"][old_index][13] == "—"
    assert data["season_availability"][old_index] is False
    assert saved_user.favorite_skaters.count() == 3
    table_players["old"].refresh_from_db()
    assert table_players["old"].goals == 1000


def test_favorite_filter_average_pagination_and_unloaded_season(client, saved_user):
    filtered = ajax(
        client, favorites="favorites_filter=true", stat_type="avg", filters="fcol[13]=>0"
    ).json()
    assert filtered["total"] == 1
    assert filtered["rows"][0][13] == 0.2
    absent = ajax(client, favorites="favorites_filter=true", season="20302031", size=1).json()
    assert absent["total"] == 3
    assert len(absent["rows"]) == 1
    assert absent["season_availability"] == [False]


def test_comparison_retains_missing_player_without_snapshot_fallback(
    client, saved_user, table_players
):
    response = client.get(reverse("comparison"), {"season": "20262027"})
    assert response.status_code == 200
    assert b"Historical Only" in response.content
    assert b"No statistics for 2026-27" in response.content
    context = response.context
    assert context["skater_rows"][2]["values"] == [2, None]  # goals
    assert context["comp_skt"][0].team.abbr == "BUF"
    assert saved_user.comparable_skaters.count() == 2


@pytest.mark.parametrize("mode", saved_players.ALLOWED_MODES["skaters"])
def test_comparison_modes_use_same_initial_and_ajax_projection(client, saved_user, mode):
    params = {"season": "20262027", "skater_mode": mode}
    page = client.get(reverse("comparison"), params)
    switched = client.get(reverse("ajax_comparison_stat_switcher", args=["skaters", mode]), params)
    assert page.status_code == switched.status_code == 200
    assert switched.json()["table"] in page.content.decode()
    assert switched.json()["season_id"] == "20262027"


def test_career_mode_supports_legacy_goalie_keys(client, saved_user, season_stats_data):
    goalie = Goalie.objects.create(
        nhl_id=88,
        games=99,
        name="Saved Goalie",
        birth_date="2000-01-01",
        career_stats={"games": 20, "goalAgainstAverage": "2.5", "savePercentage": "0.9123"},
        sbs_stats=stored_rows(season_stats_data["cases"]["current_goalie"]),
    )
    saved_user.comparable_goalies.add(goalie)
    context = saved_players.comparison_context(saved_user, "20302031", goalie_mode="career_tot")
    rows = {row["label"]: row["values"] for row in context["goalie_rows"]}
    assert rows["Games"] == [20]
    assert rows["GAA"] == ["2.50"]
    assert rows["SV %"] == ["0.912"]
    response = client.get(
        reverse("comparison"), {"season": "20302031", "goalie_mode": "career_tot"}
    )
    assert response.status_code == 200
    assert b"Saved Goalie" in response.content


def test_invalid_selection_does_not_change_saved_relationships(client, saved_user, table_players):
    target = table_players["low"]
    for url in [
        reverse("player_compare", args=[target.slug, target.nhl_id]),
        reverse("reset_comparison", args=["skaters"]),
    ]:
        assert client.post(url, query_params={"season": "invalid"}).status_code == 400
    assert saved_user.comparable_skaters.count() == 2


def test_remove_and_reset_preserve_modes_and_other_users(client, saved_user, table_players):
    other = User.objects.create_user(username="other-saved")
    other.comparable_skaters.add(table_players["low"])
    params = {"season": "20252026", "skater_mode": "career_avg"}
    low = table_players["low"]
    response = client.post(
        reverse("player_compare", args=[low.slug, low.nhl_id]), query_params=params
    )
    assert response.json()["season_id"] == "20252026"
    assert response.json()["skater_mode"] == "career_avg"
    assert response.json()["skaters_count"] == 1
    assert other.comparable_skaters.count() == 1
    assert saved_user.favorite_skaters.count() == 3
    assert (
        client.post(reverse("reset_comparison", args=["skaters"]), query_params=params).json()[
            "skaters_count"
        ]
        == 0
    )


def test_saved_pages_selector_and_anonymous_access(client, saved_user):
    assert b'data-season="20262027"' in client.get(reverse("favorites")).content
    client.logout()
    assert ajax(client, favorites="favorites_filter=true").status_code == 403
    assert client.post(reverse("reset_comparison", args=["skaters"])).status_code == 403
    assert (
        client.get(
            reverse("ajax_comparison_stat_switcher", args=["skaters", "season_tot"])
        ).status_code
        == 403
    )
    assert b"Sign In" in client.get(reverse("comparison")).content


@pytest.mark.parametrize(
    "params", [{"season": "bad"}, {"skater_mode": "bad"}, {"goalie_mode": "season_avg"}]
)
def test_invalid_comparison_parameters(client, saved_user, params):
    assert client.get(reverse("comparison"), params).status_code == 400


def test_malformed_saved_stats_and_empty_career_are_safe(client, saved_user, table_players):
    low = table_players["low"]
    low.sbs_stats = {"invalid": True}
    low.career_stats = []
    low.save(update_fields=["sbs_stats", "career_stats"])
    context = saved_players.comparison_context(saved_user, "20262027", skater_mode="career_tot")
    assert context["skater_rows"][2]["values"] == [None, None]
    assert ajax(client, favorites="favorites_filter=true").status_code == 200


def test_saved_projection_query_count_does_not_grow(saved_user, table_players):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    saved_players.comparison_context(saved_user, "20262027")  # cache profile

    def query_count():
        with CaptureQueriesContext(connection) as queries:
            saved_players.comparison_context(saved_user, "20262027")
        return len(queries)

    before = query_count()
    saved_user.comparable_skaters.add(table_players["high"], table_players["zero"])
    assert query_count() == before


def test_no_loaded_season_preserves_saved_selections(client, saved_user, table_players):
    from players.models import Skater

    Skater.objects.update(sbs_stats=[])
    response = client.get(reverse("comparison"))
    assert response.status_code == 200
    assert b"No season statistics loaded" in response.content
    assert len(response.context["comp_skt"]) == 2
    data = ajax(client, favorites="favorites_filter=true", season=None).json()
    assert data["total"] == 3
    assert data["season_availability"] == [False, False, False]


def test_other_users_favorites_are_not_exposed(client, saved_user, table_players):
    other = User.objects.create_user(username="private-favorites")
    other.favorite_skaters.add(table_players["high"])
    assert all(
        "Current High" not in name
        for name in names(ajax(client, favorites="favorites_filter=true").json())
    )


def test_goalie_only_favorites_page_and_season_table(client, saved_user, season_stats_data):
    goalie = Goalie.objects.create(
        nhl_id=99,
        games=999,
        name="Only Goalie",
        birth_date="2000-01-01",
        sbs_stats=stored_rows(season_stats_data["cases"]["current_goalie"]),
    )
    saved_user.favorite_skaters.clear()
    saved_user.favorite_goalies.add(goalie)
    response = client.get(reverse("favorites"), {"season": "20262027"})
    assert response.status_code == 200
    assert b"js_goalies_log_table" in response.content
    assert b'id="js_skaters_log_table"' not in response.content
    data = ajax(client, stat_type="gls", favorites="favorites_filter=true").json()
    assert data["total"] == 1
    assert data["rows"][0][12] != 999


def test_comparison_quota_and_anonymous_add_contract(client, saved_user, table_players):
    from players.models import Skater

    for index in range(3):
        player = Skater.objects.create(
            nhl_id=200 + index, games=0, name="Extra {}".format(index), birth_date="2000-01-01"
        )
        saved_user.comparable_skaters.add(player)
    high = table_players["high"]
    url = reverse("player_compare", args=[high.slug, high.nhl_id])
    response = client.post(url, query_params={"season": "20262027"})
    assert response.json()["comp_quota_reached"] == 1
    assert saved_user.comparable_skaters.count() == 5
    client.logout()
    assert client.post(url).json()["authenticated"] is False


@pytest.mark.parametrize(
    "player_type, mode", [("goalies", "season_avg"), ("bad", "season_tot"), ("skaters", "bad")]
)
def test_invalid_switch_modes(client, saved_user, player_type, mode):
    assert (
        client.get(reverse("ajax_comparison_stat_switcher", args=[player_type, mode])).status_code
        == 400
    )
