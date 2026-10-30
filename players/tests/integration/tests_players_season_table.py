from copy import deepcopy

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from players import utils, views
from players.management.commands import upd_pls_tot
from players.models import Goalie, Skater, Team


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def ajax(
    client,
    stat_type="tot",
    season="20262027",
    page=1,
    size=25,
    sort="col",
    filters="fcol",
    checkboxes="checkbox_filter=",
    rookie="rookie_filter=",
    favorites=None,
):
    args = [
        stat_type,
        "page={}".format(page),
        "size={}".format(size),
        sort,
        filters,
        rookie,
        checkboxes,
    ]
    if favorites:
        args.append(favorites)
    params = {"season": season} if season is not None else {}
    return client.get(reverse("ajax_players", args=args), params)


def names(data):
    return [row[utils.COLUMNS.index("name")] for row in data["rows"]]


def stored_rows(case):
    return upd_pls_tot.get_season_by_season_stats(
        deepcopy(case["landing_season_totals"]), case["position_code"]
    )


@pytest.fixture
def table_players(season_stats_data):
    buffalo = Team.objects.create(nhl_id=7, abbr="BUF", name="Buffalo Sabres")
    colorado = Team.objects.create(nhl_id=16, abbr="COL", name="Colorado Avalanche")
    low_rows = stored_rows(season_stats_data["cases"]["current_skater"])
    low_rows[0]["teamAbbr"] = "COL"
    low = Skater.objects.create(
        nhl_id=1,
        name="Current Low",
        last_name="Low",
        birth_date="2000-01-01",
        team=buffalo,
        games=999,
        goals=999,
        points=999,
        goals_avg=999,
        stats_season_id="20252026",
        sbs_stats=low_rows,
        sbs_stats_avg=[{"season": "2026-27", "goals": 999}],
        age=20,
        height_cm=180,
        height="5' 11\"",
        weight=200,
        weight_kg=91,
        nation="Canada",
        nation_abbr="CAN",
        position_abbr="D",
        position_name="Defenseman",
    )
    high_row = deepcopy(low_rows[1])
    high_row.update(gamesPlayed=5, goals=4, assists=6, points=10, hits=None, avgToi="09:00")
    high = Skater.objects.create(
        nhl_id=2,
        name="Current High",
        last_name="High",
        birth_date="1995-01-01",
        team=buffalo,
        games=0,
        goals=0,
        points=0,
        goals_avg=0,
        stats_season_id="20272028",
        sbs_stats=[high_row],
        age=30,
        height_cm=190,
        height="6' 3\"",
        weight=180,
        weight_kg=82,
        nation="Sweden",
        nation_abbr="SWE",
        position_abbr="C",
        position_name="Center",
        rookie=True,
    )
    old = Skater.objects.create(
        nhl_id=3,
        name="Historical Only",
        birth_date="1990-01-01",
        team=buffalo,
        games=80,
        goals=1000,
        points=1000,
        stats_season_id="20262027",
        sbs_stats=stored_rows(season_stats_data["cases"]["old_season_only"]),
    )
    zero = Skater.objects.create(
        nhl_id=4,
        name="Zero Games",
        birth_date="2000-01-01",
        games=99,
        sbs_stats=[dict(high_row, gamesPlayed=0)],
    )
    return {"low": low, "high": high, "old": old, "zero": zero, "BUF": buffalo, "COL": colorado}


def test_table_uses_sbs_values_before_default_sort_and_pagination(client, table_players):
    first = ajax(client, size=1).json()
    second = ajax(client, page=2, size=1).json()

    assert first["total"] == 2
    assert "Current High" in names(first)[0]
    assert first["rows"][0][0] == 1
    assert first["rows"][0][utils.COLUMNS.index("games")] == 5
    assert first["rows"][0][len(utils.COLUMNS)] == 4
    assert "Current Low" in names(second)[0]
    assert second["rows"][0][0] == 2
    assert second["rows"][0][len(utils.COLUMNS)] == 2
    assert first["season_id"] == "20262027"


def test_average_mode_derives_values_from_totals_not_snapshot_or_sbs_avg(client, table_players):
    data = ajax(client, stat_type="avg").json()
    assert "Current High" in names(data)[0]
    assert data["rows"][0][len(utils.COLUMNS)] == 0.8
    assert data["rows"][1][len(utils.COLUMNS)] == 0.2
    assert data["rows"][0][len(utils.COLUMNS) + utils.COLUMNS_AVG.index("hits_avg")] == "—"


@pytest.mark.parametrize(
    "filters, expected",
    [
        ("fcol[13]=>3", "Current High"),
        ("fcol[13]=1 - 3", "Current Low"),
        ("fcol[16]=<=-2", "Current"),
        ("fcol[2]=current low", "Current Low"),
        ("fcol[9]=18 - 25", "Current Low"),
        ("fcol[24]=>=18:00", "Current Low"),
    ],
)
def test_filters_use_selected_season_values_and_support_anonymous_ranges(
    client, table_players, filters, expected
):
    response = ajax(client, filters=filters)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert all(expected in name for name in names(data))
    if expected != "Current":
        assert data["total"] == 1


def test_decimal_average_filters_use_derived_values(client, table_players):
    data = ajax(client, stat_type="avg", filters="fcol[13]=0.1 - 0.3").json()
    assert data["total"] == 1
    assert "Current Low" in names(data)[0]


@pytest.mark.parametrize("direction", [0, 1])
def test_unknown_statistics_sort_last_in_both_directions(client, table_players, direction):
    data = ajax(client, sort="col[19]={}".format(direction)).json()
    assert "Current Low" in names(data)[0]
    assert "Current High" in names(data)[1]
    assert data["rows"][1][19] == "—"


def test_duration_sort_is_numeric_and_stable(client, table_players):
    data = ajax(client, sort="col[24]=1").json()
    assert "Current Low" in names(data)[0]
    assert "Current High" in names(data)[1]


def test_historical_selection_uses_season_team_instead_of_current_roster(client, table_players):
    data = ajax(client, season="2025-26", checkboxes='checkbox_filter={"teams":["COL"]}').json()
    assert data["total"] == 1
    assert "Current Low" in names(data)[0]
    assert data["rows"][0][13] == 20
    assert "COL" in data["rows"][0][4]
    assert "Colorado Avalanche" in data["all_teams"]
    assert data["season_id"] == "20252026"


def test_traded_player_keeps_overall_totals_when_filtering_by_participating_team(
    client, table_players, season_stats_data
):
    low = table_players["low"]
    low.sbs_stats = stored_rows(season_stats_data["cases"]["traded_skater"])
    low.save(update_fields=["sbs_stats"])

    data = ajax(client, checkboxes='checkbox_filter={"teams":["COL"]}').json()

    assert data["total"] == 1
    assert data["rows"][0][13] == 4
    assert data["rows"][0][12] == 10
    assert "TOT" in data["rows"][0][4]
    assert "COL" in data["all_teams"]


def test_checkbox_and_rookie_filters_preserve_other_selection_rules(client, table_players):
    data = ajax(
        client,
        rookie="rookie_filter=true",
        checkboxes='checkbox_filter={"nations":["Sweden"],"positions":["C"]}',
    ).json()
    assert data["total"] == 1
    assert "Current High" in names(data)[0]


def test_european_weight_filter_and_display_use_kilograms(client, table_players):
    user = User.objects.create_user(username="metric-table-user")
    user.profile.measurements_format = "Europe"
    user.profile.save()
    client.force_login(user)

    data = ajax(client, filters="fcol[7]=90 - 95").json()

    assert data["total"] == 1
    assert "Current Low" in names(data)[0]
    assert data["rows"][0][7] == 91
    assert data["height_values"] == [180]


def test_goalie_rates_come_from_sbs_and_missing_rates_render_safely(
    client, table_players, season_stats_data
):
    rows = stored_rows(season_stats_data["cases"]["current_goalie"])
    Goalie.objects.create(
        nhl_id=10,
        name="Season Goalie",
        birth_date="2000-01-01",
        games=99,
        wins=99,
        goals_against_av=9.99,
        saves_perc=0.111,
        sbs_stats=rows,
    )
    Goalie.objects.create(
        nhl_id=11,
        name="Missing Rates",
        birth_date="2000-01-01",
        games=99,
        sbs_stats=[dict(rows[0], wins=1, goalsAgainstAvg=None, savePctg=None)],
    )

    data = ajax(client, stat_type="gls").json()

    assert data["total"] == 2
    assert "Season Goalie" in names(data)[0]
    assert data["rows"][0][13] == 2
    assert data["rows"][0][16:18] == ["2.50", "0.900"]
    assert data["rows"][1][16:18] == ["—", "—"]


def test_empty_requested_season_never_falls_back_to_previous_statistics(client, table_players):
    response = ajax(client, season="20272028", size="All")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["rows"] == []
    assert data["season_id"] == "20272028"
    assert "2027-28" in data["empty_message"]
    assert data["age_range"] == [None, None]
    assert data["height_values"] == {}


def test_default_season_comes_from_sbs_and_is_displayed_in_page_and_ajax(client, table_players):
    page = client.get(reverse("players"))
    assert page.status_code == 200
    assert page.context["season_id"] == "20262027"
    assert b'data-season="20262027"' in page.content
    assert b"2026-27" in page.content
    data = ajax(client, season=None).json()
    assert data["season_id"] == page.context["season_id"]
    assert data["total"] == 2


def test_unloaded_season_remains_selected_on_page(client, table_players):
    page = client.get(reverse("players"), {"season": "20272028"})
    assert page.context["season_id"] == "20272028"
    assert b'value="20272028" selected' in page.content


def test_empty_database_has_a_clear_empty_state(client):
    page = client.get(reverse("players"))
    data = ajax(client, season=None).json()
    assert page.status_code == 200
    assert b"No seasons loaded" in page.content
    assert data["total"] == 0
    assert data["season_id"] is None
    assert data["empty_message"] == "No player statistics have been loaded."


@pytest.mark.parametrize(
    "kwargs",
    [
        {"season": "invalid"},
        {"page": 0},
        {"size": 0},
        {"stat_type": "unknown"},
        {"sort": "col[99]=0"},
        {"filters": "fcol[99]=1"},
        {"checkboxes": "checkbox_filter=[]"},
    ],
)
def test_invalid_table_requests_return_bad_request(client, table_players, kwargs):
    assert ajax(client, **kwargs).status_code == 400


def test_projection_does_not_write_snapshots_or_history(client, table_players):
    low = table_players["low"]
    before = deepcopy(low.sbs_stats)
    ajax(client)
    low.refresh_from_db()
    assert low.goals == 999
    assert low.games == 999
    assert low.stats_season_id == "20252026"
    assert low.sbs_stats == before


def test_query_count_does_not_grow_with_player_count(table_players):
    request = RequestFactory().get("/", {"season": "20262027"})
    request.user = AnonymousUser()

    def query_count():
        with CaptureQueriesContext(connection) as captured:
            response = views.ajax_players(
                request,
                "tot",
                "page=1",
                "size=All",
                "col",
                "fcol",
                "rookie_filter=",
                "checkbox_filter=",
            )
            assert response.status_code == 200
        return len(captured)

    before = query_count()
    low = table_players["low"]
    for index in range(10):
        Skater.objects.create(
            nhl_id=100 + index,
            name="Extra {}".format(index),
            birth_date="2000-01-01",
            games=0,
            sbs_stats=deepcopy(low.sbs_stats),
        )
    assert query_count() == before


def test_favorites_endpoint_keeps_its_existing_source_until_its_integration(client, table_players):
    user = User.objects.create_user(username="saved-table-user")
    user.favorite_skaters.add(table_players["low"])
    client.force_login(user)

    response = ajax(client, favorites="favorites_filter=true")

    assert response.status_code == 200
    assert response.json()["rows"][0][13] == 999


def test_main_table_favorite_stars_use_current_user_membership(client, table_players):
    user = User.objects.create_user(username="main-table-user")
    user.favorite_skaters.add(table_players["low"])
    client.force_login(user)

    data = ajax(client).json()

    assert "Current High" in names(data)[0]
    assert "js-fav-add" in data["rows"][0][1]
    assert "Current Low" in names(data)[1]
    assert "js-fav-del" in data["rows"][1][1]
