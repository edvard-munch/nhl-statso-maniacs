"""Real AJAX responses must carry escaped cells without rewriting stored data."""

from django.contrib.auth.models import User
from django.urls import reverse
import pytest

from players import utils
from players.models import Goalie, Skater
from players.tests.integration.tests_players_season_table import ajax, table_players  # noqa: F401
from players.tests.unit.other.tests_table_rendering import Cell

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("mode", ["tot", "avg"])
def test_players_ajax_escapes_stored_names_and_nationality(
    client, table_players, mode, requests_mock
):
    player = table_players["low"]
    player.name = '<img src=x onerror="player()"> & Player'
    player.nation_abbr = "C&N"
    player.nation = "<script>nation()</script>"
    player.save(update_fields=["name", "nation_abbr", "nation"])
    before = Skater.objects.values().get(pk=player.pk)
    response = ajax(client, stat_type=mode)
    assert response.status_code == 200
    name_index = utils.COLUMNS.index("name")
    row = next(row for row in response.json()["rows"] if player.slug in row[name_index])
    name = Cell(row[name_index])
    assert "".join(name.text) == player.name
    assert name.tags == [
        ("td", {"class": "name"}),
        ("a", {"class": "name", "href": f"//testserver/player/{player.slug}/{player.nhl_id}"}),
    ]
    nation = Cell(row[utils.COLUMNS.index("nation_abbr")])
    assert [tag for tag, attrs in nation.tags] == ["td", "span"]
    assert "".join(nation.text) == player.nation_abbr + player.nation
    assert Skater.objects.values().get(pk=player.pk) == before


@pytest.mark.parametrize("model, mode", [(Skater, "skt_log"), (Goalie, "gls_log")])
@pytest.mark.parametrize("missing", [False, True])
def test_favorite_gamelog_ajax_escapes_cells_and_preserves_missing_stats(
    client, model, mode, missing, requests_mock
):
    user = User.objects.create_user(username="rendering-viewer")
    game = {
        "player": {"name": "<b>Literal & Player</b>", "slug": "literal-player", "nhl_id": 42},
        "team": {"abbr": "B&F", "name": "<script>team()</script>"},
        "opponent": {"abbr": "O&P", "name": '<img src=x onerror="opponent()">'},
        "format_date": "Nov 3",
        "goals": 0,
        "goalsAgainst": 0,
    }
    if not missing:
        game["savePercentage"] = None
    player = model.objects.create(
        nhl_id=42,
        name="Literal Player",
        birth_date="2000-01-01",
        games=1,
        gamelog_stats={"game": game},
    )
    player.favoriting.add(user)
    before = model.objects.values().get(pk=player.pk)
    client.force_login(user)
    response = client.get(
        reverse("ajax_fav_players_gamelog", args=[mode, "page=1", "size=25", "col", "fcol"])
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    row = response.json()["rows"][0]
    assert "".join(Cell(row[0]).text) == game["player"]["name"]
    for index, kind in [(1, "team"), (3, "opponent")]:
        cell = Cell(row[index])
        assert [tag for tag, attrs in cell.tags] == ["td", "span"]
        assert "".join(cell.text) == game[kind]["abbr"] + game[kind]["name"]
    if mode == "gls_log":
        assert row[6:9] == [0, "—", "—"]
    else:
        assert row[4:6] == [0, "—"]
    assert model.objects.values().get(pk=player.pk) == before
