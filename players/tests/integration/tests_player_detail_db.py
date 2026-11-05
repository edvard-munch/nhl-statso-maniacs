"""Rendered player profiles and gamelogs from isolated saved season fixtures."""

from copy import deepcopy
from datetime import date

from django.urls import reverse
import pytest

from players import utils
from players.tests.integration.tests_team_season_tables import TableRows
from players.tests.unit.tests_readonly_db.conftest import no_live_http, view_data  # noqa: F401


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(params=["skater", "goalie"])
def detail_data(request, view_data, monkeypatch):
    monkeypatch.setattr(utils, "season_in_prog", lambda: False)
    player = view_data[request.param]
    if request.param == "skater":
        player.goals = 777  # Snapshot differs deliberately from career rows/totals.
        player.sbs_stats_avg = [
            dict(row, goals=0.25 if index == 0 else 0.2)
            for index, row in enumerate(player.sbs_stats)
        ]
        player.career_stats = {
            "gamesPlayed": 90,
            "goals": 22,
            "hits": 68,
            "powerPlayTimeOnIcePerGame": "02:05",
        }
        player.career_stats_avg = {"gamesPlayed": 90, "goals": 0.24, "hits": 0.76}
    else:
        player.saves = 8888
        player.career_stats = {
            "gamesPlayed": 40,
            "wins": 20,
            "losses": 15,
            "otLosses": 5,
            "goalsAgainstAvg": 2.125,
            "savePctg": 0.9123,
            "saves": 1234,
            "shutouts": 3,
        }
    player.save()
    return player


def page(client, player, route="player_detail", **params):
    return client.get(reverse(route, args=[player.slug, player.nhl_id]), params)


def test_career_tables_render_saved_rows_and_separate_totals(client, detail_data):
    player = detail_data
    response = page(client, player)
    assert response.status_code == 200
    html = response.content.decode()
    if player.position_abbr == "G":
        rows = TableRows(html, "tab1").rows
        assert rows[0] == ["2026-27", "BUF", "4", "2", "1", "1", "2.50", "0.900", "90", "0"]
        assert rows[-1] == ["Total", "—", "40", "20", "15", "5", "2.13", "0.912", "1234", "3"]
        assert not response.context["skater"]
    else:
        rows = TableRows(html, "tab2").rows
        assert rows[0][:4] == ["2025-26", "BUF", "80", "20"]
        assert rows[1][:4] == ["2026-27", "BUF", "10", "2"]
        assert rows[2][:4] == ["Total", "—", "90", "22"]
        assert rows[2][-2] == "02:05"
        assert rows[3][:4] == ["2025-26", "BUF", "80", "0.25"]
        assert rows[4][:4] == ["2026-27", "BUF", "10", "0.2"]
        assert rows[5][:4] == ["Total", "—", "90", "0.24"]
        assert "777" not in " ".join(cell for row in rows for cell in row)


@pytest.mark.parametrize(
    "marker,games,visible",
    [("20262027", 4, True), ("20252026", 80, False), (None, 80, False), ("20262027", 0, False)],
)
def test_current_panel_requires_current_marker_and_games(
    client, detail_data, marker, games, visible
):
    detail_data.stats_season_id = marker
    detail_data.games = games
    detail_data.save()
    response = page(client, detail_data)
    assert response.context["show_current_stats"] is visible
    html = response.content.decode()
    assert ("Current-season stats are not available for this player." in html) is not visible
    assert ">Career<" in html
    snapshot = "8888" if detail_data.position_abbr == "G" else "777"
    assert (snapshot in html) is visible


def test_detail_season_parameter_does_not_rewrite_career_history(client, detail_data):
    # The current profile has no season selector; table selectors belong to other views.
    before = type(detail_data).objects.values().get(pk=detail_data.pk)
    response = page(client, detail_data, season="20252026")
    assert response.context["player"].sbs_stats == before["sbs_stats"]
    assert response.context["show_current_stats"] is True
    assert type(detail_data).objects.values().get(pk=detail_data.pk) == before


def set_logs(player, count):
    prototype = deepcopy(next(iter(player.gamelog_stats.values())))
    entries = {}
    # Insert oldest first so chronological rendering cannot rely on JSON insertion order.
    for day in range(1, count + 1):
        entry = deepcopy(prototype)
        entry.update(
            format_date=f"Log {day:02}",
            toi="19:43",
            powerPlayToi="02:14",
            shorthandedToi="02:29",
            decision="W",
            savePctg=0.923,
            saveShotsAgainst="24/26",
            shutout=0,
        )
        entries[str(date(2026, 10, day))] = entry
    player.gamelog_stats = entries
    player.save(update_fields=["gamelog_stats"])


def test_recent_and_full_logs_render_newest_first_with_actual_game_times(client, detail_data):
    set_logs(detail_data, 7)
    before = deepcopy(detail_data.gamelog_stats)
    detail = page(client, detail_data)
    assert [r["format_date"] for r in detail.context["last_gms"]] == [
        "Log 07",
        "Log 06",
        "Log 05",
        "Log 04",
        "Log 03",
    ]
    assert b"Log 02" not in detail.content
    log = page(client, detail_data, "player_gamelog")
    rows = TableRows(
        log.content.decode(), "tab1" if detail_data.position_abbr == "G" else "tab2"
    ).rows
    assert [row[0] for row in rows] == [f"Log {day:02}" for day in range(7, 0, -1)]
    if detail_data.position_abbr == "G":
        assert rows[0][2:] == ["W", "19:43", "0", "0.923", "24/26", "0"]
    else:
        assert rows[0][-3:] == ["19:43", "02:14", "02:29"]
        assert b"02:14" in detail.content and b"02:29" in detail.content
    detail_data.refresh_from_db()
    assert detail_data.gamelog_stats == before
    assert (
        reverse("player_detail", args=[detail_data.slug, detail_data.nhl_id]).encode()
        in log.content
    )


@pytest.mark.parametrize("count,pager", [(25, False), (26, True)])
def test_full_gamelog_pager_boundary(client, detail_data, count, pager):
    set_logs(detail_data, count)
    response = page(client, detail_data, "player_gamelog")
    assert response.context["pager"] is pager
    assert len(response.context["gamelog"]) == count
    assert (b"<tfoot>" in response.content) is pager


def test_empty_profile_history_and_gamelog_render_without_inventing_rows(client, detail_data):
    detail_data.sbs_stats = []
    detail_data.career_stats = {}
    detail_data.gamelog_stats = {}
    detail_data.stats_season_id = None
    if detail_data.position_abbr != "G":
        detail_data.sbs_stats_avg = []
        detail_data.career_stats_avg = {}
    detail_data.save()
    detail = page(client, detail_data)
    assert detail.status_code == 200
    assert detail.context["last_gms"] == []
    assert not detail.context["show_current_stats"]
    assert b"2026-27" not in detail.content
    log = page(client, detail_data, "player_gamelog")
    assert log.status_code == 200
    assert log.context["gamelog"] == []
    assert not log.context["pager"]
    assert (
        TableRows(log.content.decode(), "tab1" if detail_data.position_abbr == "G" else "tab2").rows
        == []
    )


@pytest.mark.parametrize("route", ["player_detail", "player_gamelog"])
@pytest.mark.parametrize("invalid", ["slug", "id"])
def test_invalid_player_identity_returns_404(client, view_data, route, invalid):
    player = view_data["skater"]
    args = [
        "wrong-slug" if invalid == "slug" else player.slug,
        99999999 if invalid == "id" else player.nhl_id,
    ]
    assert client.get(reverse(route, args=args)).status_code == 404
