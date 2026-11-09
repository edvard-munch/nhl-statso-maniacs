"""Rendered game stats and scoreboard navigation from isolated saved games."""

from copy import deepcopy
from datetime import date
import re

from django.contrib.auth.models import User
from django.urls import reverse
import pytest

from players import utils
from players.models import Game, Gameday, Skater
from players.tests.integration.tests_team_season_tables import TableRows
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game, load  # noqa: F401


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline_http(requests_mock):
    # requests-mock rejects any unregistered request, including during view rendering.
    return requests_mock


@pytest.fixture
def game_page(loaded_game):
    fixture = loaded_game
    fixture.game = load(fixture)
    for index, key in enumerate(
        ("away_forward", "away_defense", "home_forward", "home_defense"), 1
    ):
        player = fixture.players[key]
        player.refresh_from_db()
        player.goals = 999
        player.gamelog_stats[fixture.day["date"]].update(
            goals=index, toi="12:34", powerPlayToi=f"01:0{index}", shorthandedToi=f"02:0{index}"
        )
        player.gamelog_stats["2026-11-20"] = dict(
            player.gamelog_stats[fixture.day["date"]], goals=88, powerPlayToi="09:59"
        )
        player.save()
    for key in ("away_goalie", "home_goalie"):
        player = fixture.players[key]
        player.refresh_from_db()
        player.saves = 9999
        player.gamelog_stats[fixture.day["date"]].update(
            decision="W" if key == "away_goalie" else "L",
            toi="60:00",
            goalsAgainst=2,
            savePctg=0.923,
            saveShotsAgainst="24/26",
        )
        player.save()
    return fixture


def game_url(game):
    return reverse("game_detail", args=[game.slug, game.nhl_id])


def test_game_tables_use_game_date_rosters_and_stats_not_current_snapshots(
    client, game_page, requests_mock
):
    fixture = game_page
    count = requests_mock.call_count
    response = client.get(game_url(fixture.game))
    assert response.status_code == 200
    assert requests_mock.call_count == count
    html = response.content.decode()
    for index, (table, key) in enumerate(
        [
            ("away_fwds", "away_forward"),
            ("away_d_men", "away_defense"),
            ("home_fwds", "home_forward"),
            ("home_d_men", "home_defense"),
        ],
        1,
    ):
        rows = TableRows(html, table).rows
        assert len(rows) == 1
        assert len(rows[0]) == 18
        assert rows[0][2] == fixture.players[key].name
        assert rows[0][5] == str(index)
        assert rows[0][-3:] == ["12:34", f"01:0{index}", f"02:0{index}"]
        assert (
            reverse("player_detail", args=[fixture.players[key].slug, fixture.players[key].nhl_id])
            in html
        )
    goalie_rows = TableRows(html, "away_goalies").rows + TableRows(html, "home_goalies").rows
    assert len(goalie_rows) == 2
    assert goalie_rows[0][4:] == ["W", "60:00", "2", "0.923", "24/26"]
    assert goalie_rows[1][4:] == ["L", "60:00", "2", "0.923", "24/26"]
    assert "09:59" not in html and "9999" not in html
    assert fixture.away.name in html and fixture.home.name in html


def test_game_forward_rows_keep_last_name_sorting(client, game_page):
    fixture = game_page
    existing = fixture.players["away_forward"]
    existing.last_name = "Zulu"
    existing.save(update_fields=["last_name"])
    existing.refresh_from_db()
    first = Skater.objects.create(
        nhl_id=990009,
        name="First Alphabetic",
        last_name="Aardvark",
        games=999,
        birth_date="2000-01-01",
        position_abbr="C",
        gamelog_stats=deepcopy(existing.gamelog_stats),
    )
    fixture.game.away_forwards.add(first)
    response = client.get(game_url(fixture.game))
    assert [r[2] for r in TableRows(response.content.decode(), "away_fwds").rows] == [
        "First Alphabetic",
        existing.name,
    ]


@pytest.mark.parametrize("signed_in", [False, True])
def test_game_favorites_are_private_to_the_current_viewer(client, game_page, signed_in):
    fixture = game_page
    if signed_in:
        viewer = User.objects.create_user(username="other-game-viewer")
        viewer.favorite_skaters.add(fixture.players["home_defense"])
        client.force_login(viewer)
    response = client.get(game_url(fixture.game))
    links = dict(
        (url, action)
        for action, url in re.findall(
            r'<a class="(js-fav-(?:add|del))" href="([^"]+)"', response.content.decode()
        )
    )
    for key in ("away_forward", "home_defense"):
        player = fixture.players[key]
        target = reverse("player_favorite", args=[player.slug, player.nhl_id])
        assert links[target] == (
            "js-fav-del" if signed_in and key == "home_defense" else "js-fav-add"
        )
    assert list(fixture.user.favorite_skaters.all()) == [fixture.players["away_forward"]]


@pytest.mark.parametrize("missing", ["row", "roster"])
def test_missing_game_statistics_never_fall_back_to_season_snapshot(client, game_page, missing):
    fixture = game_page
    if missing == "roster":
        fixture.game.away_forwards.clear()
    else:
        player = fixture.players["away_forward"]
        player.refresh_from_db()
        player.gamelog_stats.pop(fixture.day["date"])
        player.save(update_fields=["gamelog_stats"])
    response = client.get(game_url(fixture.game))
    assert response.status_code == 200
    rows = TableRows(response.content.decode(), "away_fwds").rows
    if missing == "roster":
        assert rows == []
    else:
        assert rows[0][5:] == [""] * 13


@pytest.mark.parametrize("invalid", ["slug", "id"])
def test_missing_game_identity_returns_404(client, game_page, invalid):
    game = game_page.game
    args = [
        "wrong-slug" if invalid == "slug" else game.slug,
        99999999 if invalid == "id" else game.nhl_id,
    ]
    assert client.get(reverse("game_detail", args=args)).status_code == 404


@pytest.fixture
def scoreboard_days():
    # Deliberately insert a middle date last: database PK order is not date order.
    values = [1, 2, 3, 4, 6, 7, 8, 9, 5]
    days = {n: Gameday.objects.create(day=date(2026, 10, n)) for n in values}
    for n, day in days.items():
        Game.objects.create(
            nhl_id=2026020000 + n,
            slug=f"fixture-game-{n}",
            gameday=day,
            result=f"Scoreboard fixture {n}",
        )
    return days


@pytest.mark.parametrize(
    "selected,expected", [(1, [1, 2, 3, 4, 5, 6]), (5, [2, 3, 4, 5, 6, 7]), (9, [4, 5, 6, 7, 8, 9])]
)
def test_scoreboard_navigation_window_and_selected_game_links(
    client, scoreboard_days, selected, expected
):
    response = client.get(reverse("games", args=[f"2026-10-{selected:02}"]))
    assert response.status_code == 200
    assert response.context["today"] == scoreboard_days[selected]
    assert [d.day.day for d in response.context["days_per_page"]] == expected
    html = response.content.decode()
    for n in expected:
        assert reverse("games", args=[f"2026-10-{n:02}"]) in html
    selected_game = scoreboard_days[selected].games.get()
    assert game_url(selected_game) in html
    assert f"Scoreboard fixture {selected}" in html
    assert "curr-day" in html
    assert "Scoreboard fixture " + str(2 if selected == 1 else 1) not in html


def test_unknown_valid_date_falls_back_to_latest_calendar_day(client, scoreboard_days):
    response = client.get(reverse("games", args=["2000-01-01"]))
    assert response.context["today"] == scoreboard_days[9]
    assert b"Scoreboard fixture 9" in response.content


def test_default_scoreboard_date_is_evaluated_for_each_request(
    client, scoreboard_days, monkeypatch
):
    for day in (2, 8):
        monkeypatch.setattr(utils, "get_us_pacific_date", lambda day=day: f"2026-10-{day:02}")
        response = client.get(reverse("games"))
        assert response.context["today"] == scoreboard_days[day]


@pytest.mark.parametrize("invalid", ["not-a-date", "2026-02-30"])
def test_invalid_scoreboard_date_returns_404(client, scoreboard_days, invalid):
    assert client.get(reverse("games", args=[invalid])).status_code == 404


def test_empty_scoreboard_renders_without_inventing_games(client):
    response = client.get(reverse("games", args=["2026-10-01"]))
    assert response.status_code == 200
    assert response.context["today"] is None
    assert response.context["days_per_page"] == []
    assert b"NHL Scoreboard" in response.content
    assert b"/game/" not in response.content
