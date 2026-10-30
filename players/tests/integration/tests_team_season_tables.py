from copy import deepcopy
from html.parser import HTMLParser

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from players import views
from players.management.commands import upd_pls_tot
from players.models import Goalie, Skater, Team


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class TableRows(HTMLParser):
    """Inspect rendered table cells, including AJAX fragments, without a browser."""

    def __init__(self, html, table_id=None):
        super().__init__()
        self.target = table_id
        self.table = None
        self.recording = table_id is None
        self.rows = []
        self.row = None
        self.cell = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = dict(attrs).get("id")
        if tag == "tbody":
            self.recording = self.table == self.target
        if tag == "tr" and self.recording:
            self.row = []
        if tag == "td" and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag == "tbody":
            self.recording = False


def page(client, team, season="20262027"):
    return client.get(
        reverse("team_detail", args=[team.slug, team.nhl_id]),
        {"season": season} if season is not None else {},
    )


def ajax(client, team, mode="tot", position="t", season="20262027"):
    return client.get(
        reverse("ajax_stats_switcher", args=[team.slug, team.nhl_id, mode, position]),
        {"season": season} if season is not None else {},
    )


def stored(case):
    return upd_pls_tot.get_season_by_season_stats(
        deepcopy(case["landing_season_totals"]), case["position_code"]
    )


@pytest.fixture
def team_players(season_stats_data):
    buffalo = Team.objects.create(nhl_id=7, abbr="BUF", name="Buffalo Sabres")
    colorado = Team.objects.create(nhl_id=16, abbr="COL", name="Colorado Avalanche")
    current = stored(season_stats_data["cases"]["current_skater"])
    defender = Skater.objects.create(
        nhl_id=1,
        name="Season Defender",
        last_name="Defender",
        birth_date="2000-01-02",
        team=buffalo,
        games=999,
        goals=999,
        points=999,
        goals_avg=999,
        sbs_stats=current,
        sbs_stats_avg=[{"season": "2026-27", "goals": 999}],
        stats_season_id="20272028",
        position_abbr="D",
        pl_number=10,
        height="6' 0\"",
        height_cm=183,
        weight=200,
        weight_kg=91,
    )
    traded = Skater.objects.create(
        nhl_id=2,
        name="Traded Forward",
        last_name="Forward",
        birth_date="2000-01-02",
        team=colorado,
        games=100,
        goals=999,
        points=999,
        goals_avg=999,
        sbs_stats=stored(season_stats_data["cases"]["traded_skater"]),
        position_abbr="C",
        pl_number=20,
    )
    missing = Skater.objects.create(
        nhl_id=3,
        name="Missing Fields",
        last_name="Missing",
        birth_date="2000-01-02",
        team=buffalo,
        games=100,
        hits=999,
        faceoff_wins=999,
        position_abbr="LW",
        sbs_stats=stored(season_stats_data["cases"]["missing_enrichment"]),
    )
    historical = Skater.objects.create(
        nhl_id=4,
        name="Historical Only",
        birth_date="1990-01-01",
        team=buffalo,
        games=100,
        goals=999,
        stats_season_id="20262027",
        position_abbr="D",
        sbs_stats=stored(season_stats_data["cases"]["old_season_only"]),
    )
    for nhl_id, name, rows in (
        (5, "No Season Data", None),
        (6, "Other Team Only", [dict(current[1], teamAbbr="COL")]),
        (7, "Zero Games", [dict(current[1], gamesPlayed=0)]),
        (8, "Combined Only", [dict(current[1], teamAbbr="TOT")]),
    ):
        Skater.objects.create(
            nhl_id=nhl_id,
            name=name,
            birth_date="2000-01-01",
            team=buffalo,
            games=100,
            goals=999,
            position_abbr="C",
            sbs_stats=rows,
        )
    goalie_rows = stored(season_stats_data["cases"]["current_goalie"])
    buffalo_row = goalie_rows[0]
    goalie_rows += [
        dict(
            buffalo_row,
            teamAbbr="COL",
            gamesPlayed=2,
            wins=1,
            losses=1,
            otLosses=0,
            goalsAgainstAvg=5.0,
            savePctg=0.8,
            shotsAgainst=50,
            goalsAgainst=10,
            saves=40,
        ),
        dict(
            buffalo_row,
            teamAbbr="TOT",
            gamesPlayed=6,
            wins=3,
            losses=2,
            otLosses=1,
            goalsAgainstAvg=3.33,
            savePctg=0.867,
            shotsAgainst=150,
            goalsAgainst=20,
            saves=130,
        ),
    ]
    goalie = Goalie.objects.create(
        nhl_id=10,
        name="Traded Goalie",
        birth_date="2000-01-01",
        team=colorado,
        games=99,
        wins=99,
        goals_against_av=9.99,
        saves_perc=0.111,
        position_abbr="G",
        sbs_stats=goalie_rows,
    )
    missing_goalie = Goalie.objects.create(
        nhl_id=11,
        name="Missing Goalie Rates",
        birth_date="2000-01-01",
        team=buffalo,
        games=99,
        wins=99,
        position_abbr="G",
        sbs_stats=[dict(buffalo_row, wins=0, goalsAgainstAvg=None, savePctg=None)],
    )
    return {
        "BUF": buffalo,
        "COL": colorado,
        "defender": defender,
        "traded": traded,
        "missing": missing,
        "historical": historical,
        "goalie": goalie,
        "missing_goalie": missing_goalie,
    }


def test_initial_page_uses_team_season_contributions_not_roster_or_snapshot(client, team_players):
    response = page(client, team_players["BUF"])

    assert response.status_code == 200
    defenders = TableRows(response.content.decode(), "tab2").rows
    forwards = TableRows(response.content.decode(), "tab3").rows
    assert [row[3] for row in defenders] == ["Season Defender"]
    assert [row[3] for row in forwards] == ["Traded Forward", "Missing Fields"]
    assert defenders[0][11:15] == ["10", "2", "3", "5"]
    assert forwards[0][11:15] == ["6", "3", "3", "6"]
    assert len(defenders[0]) == 26
    assert len(forwards[0]) == 26
    for name in (
        "Historical Only",
        "No Season Data",
        "Other Team Only",
        "Zero Games",
        "Combined Only",
    ):
        assert name not in response.content.decode()


def test_goalie_rows_use_exact_team_rates_and_valid_table_markup(client, team_players):
    response = page(client, team_players["BUF"])
    rows = TableRows(response.content.decode(), "tab1").rows

    assert [row[3] for row in rows] == ["Traded Goalie", "Missing Goalie Rates"]
    assert rows[0][11:19] == ["4", "2", "1", "1", "2.50", "0.900", "90", "0"]
    assert rows[1][12] == "0"
    assert rows[1][15:17] == ["—", "—"]
    assert all(len(row) == 19 for row in rows)


@pytest.mark.parametrize("position, table_id", [("d", "tab2"), ("f", "tab3")])
def test_initial_and_ajax_totals_are_identical(client, team_players, position, table_id):
    initial = page(client, team_players["BUF"])
    response = ajax(client, team_players["BUF"], position=position)

    assert response.status_code == 200
    assert (
        TableRows(response.json()["stats"]).rows
        == TableRows(initial.content.decode(), table_id).rows
    )
    assert response.json()["season_id"] == "20262027"
    assert response.json()["position_filter"] == position


def test_averages_use_the_teams_games_and_ignore_stored_averages(client, team_players):
    data = ajax(client, team_players["BUF"], mode="avg").json()
    rows = {row[3]: row for row in TableRows(data["stats"]).rows}

    assert rows["Traded Forward"][11:15] == ["6", "0.5", "0.5", "1.0"]
    assert rows["Season Defender"][11:15] == ["10", "0.2", "0.3", "0.5"]
    assert rows["Missing Fields"][12] == "0.0"
    assert rows["Missing Fields"][18:21] == ["—", "—", "—"]
    assert data["stat_type"] == "avg"


def test_joined_mode_contains_each_split_group_once(client, team_players):
    team = team_players["BUF"]
    defenders = TableRows(ajax(client, team, position="d").json()["stats"]).rows
    forwards = TableRows(ajax(client, team, position="f").json()["stats"]).rows
    joined = TableRows(ajax(client, team).json()["stats"]).rows

    assert len(joined) == len(defenders) + len(forwards) == 3
    assert {row[3] for row in joined} == {row[3] for row in defenders + forwards}
    assert joined[0][3] == "Traded Forward"


def test_other_team_uses_its_own_split_not_current_roster_totals(client, team_players):
    data = ajax(client, team_players["COL"], position="f").json()
    rows = {row[3]: row for row in TableRows(data["stats"]).rows}

    assert rows["Traded Forward"][11:15] == ["4", "1", "2", "3"]
    assert rows["Other Team Only"][11:15] == ["10", "2", "3", "5"]


def test_historical_selection_is_shared_by_page_and_ajax(client, team_players):
    initial = page(client, team_players["BUF"], season="2025-26")
    data = ajax(client, team_players["BUF"], position="d", season="20252026").json()

    assert initial.context["season_id"] == "20252026"
    assert TableRows(initial.content.decode(), "tab2").rows == TableRows(data["stats"]).rows
    assert {row[3] for row in TableRows(data["stats"]).rows} == {
        "Season Defender",
        "Historical Only",
    }
    assert all(row[11:15] == ["80", "20", "30", "50"] for row in TableRows(data["stats"]).rows)
    assert b"?season=20252026" in initial.content


def test_global_default_season_matches_players_page_and_ajax(client, team_players):
    initial = page(client, team_players["BUF"], season=None)
    players = client.get(reverse("players"))
    data = ajax(client, team_players["BUF"], season=None).json()

    assert (
        initial.context["season_id"]
        == players.context["season_id"]
        == data["season_id"]
        == "20262027"
    )
    assert b'data-season="20262027"' in initial.content
    assert b'data-mode="tot"' in initial.content
    assert b"?season=20262027" in initial.content


@pytest.mark.parametrize("position", ["d", "f", "t"])
def test_unloaded_season_stays_empty_for_all_switches(client, team_players, position):
    initial = page(client, team_players["BUF"], season="20272028")
    data = ajax(
        client, team_players["BUF"], mode="avg", position=position, season="20272028"
    ).json()

    assert initial.context["season_id"] == "20272028"
    assert b'value="20272028" selected' in initial.content
    assert TableRows(initial.content.decode(), "tab1").rows == []
    assert TableRows(initial.content.decode(), "tab2").rows == []
    assert TableRows(initial.content.decode(), "tab3").rows == []
    assert data["stats"].strip() == ""
    assert data["total"] == 0
    assert "2027-28" in data["empty_message"]


def test_team_with_only_history_does_not_choose_an_older_default(client, team_players):
    team = Team.objects.create(nhl_id=55, abbr="HIS", name="Historical Team")
    Skater.objects.create(
        nhl_id=100,
        name="Former Player",
        birth_date="1990-01-01",
        games=99,
        sbs_stats=[{"season": "2025-26", "teamAbbr": "HIS", "gamesPlayed": 10, "goals": 2}],
    )

    initial = page(client, team, season=None)
    data = ajax(client, team, season=None).json()

    assert initial.context["season_id"] == data["season_id"] == "20262027"
    assert data["total"] == 0
    assert "Former Player" not in initial.content.decode()


def test_empty_database_renders_without_logo_or_season(client):
    team = Team.objects.create(nhl_id=7, abbr="BUF", name="Buffalo Sabres")
    response = page(client, team, season=None)
    data = ajax(client, team, season=None).json()

    assert response.status_code == 200
    assert b"No seasons loaded" in response.content
    assert data["season_id"] is None
    assert data["total"] == 0


@pytest.mark.parametrize(
    "mode, position, season",
    [
        ("bad", "d", "20262027"),
        ("tot", "bad", "20262027"),
        ("avg", "default", "20262027"),
        ("tot", "t", "invalid"),
    ],
)
def test_invalid_ajax_selection_returns_bad_request(client, team_players, mode, position, season):
    assert ajax(client, team_players["BUF"], mode, position, season).status_code == 400


def test_invalid_page_season_returns_bad_request(client, team_players):
    assert page(client, team_players["BUF"], season="invalid").status_code == 400


def test_unknown_team_and_wrong_slug_still_return_not_found(client):
    response = client.get(reverse("ajax_stats_switcher", args=["missing", 999, "tot", "t"]))
    assert response.status_code == 404
    team = Team.objects.create(nhl_id=7, name="Buffalo Sabres", abbr="BUF")
    assert client.get(reverse("team_detail", args=["wrong-slug", team.nhl_id])).status_code == 404


def test_metric_units_and_favorite_stars_match_after_ajax(client, team_players):
    user = User.objects.create_user(username="team-table-user")
    user.profile.measurements_format = "Europe"
    user.profile.save()
    user.favorite_skaters.add(team_players["defender"])
    user.favorite_goalies.add(team_players["goalie"])
    client.force_login(user)

    initial = page(client, team_players["BUF"])
    data = ajax(client, team_players["BUF"], position="d").json()
    rows = TableRows(data["stats"]).rows

    assert rows[0][6:8] == ["183", "91"]
    assert 'class="js-fav-del"' in data["stats"]
    assert 'class="js-fav-del"' in initial.content.decode()
    assert TableRows(initial.content.decode(), "tab2").rows == rows
    team_players["defender"].refresh_from_db()
    assert team_players["defender"].height == "6' 0\""
    assert team_players["defender"].weight == 200


def test_team_reads_leave_snapshots_and_history_untouched(client, team_players):
    defender = team_players["defender"]
    before = deepcopy(defender.sbs_stats)
    page(client, team_players["BUF"])
    ajax(client, team_players["BUF"], mode="avg")

    defender.refresh_from_db()
    assert defender.games == 999
    assert defender.goals == 999
    assert defender.stats_season_id == "20272028"
    assert defender.sbs_stats == before


def test_team_query_count_does_not_grow_with_rendered_players(team_players):
    team = team_players["BUF"]
    request = RequestFactory().get("/", {"season": "20262027"})
    request.user = AnonymousUser()

    def count():
        with CaptureQueriesContext(connection) as captured:
            response = views.team_detail(request, team.slug, team.nhl_id)
            assert response.status_code == 200
        return len(captured)

    before = count()
    for index in range(10):
        Skater.objects.create(
            nhl_id=100 + index,
            name="Extra {}".format(index),
            birth_date="2000-01-01",
            games=99,
            position_abbr="D",
            sbs_stats=deepcopy(team_players["defender"].sbs_stats),
        )
    assert count() == before
