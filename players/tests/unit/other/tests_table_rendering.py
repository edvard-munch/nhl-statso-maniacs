"""Table cells preserve literal text, balanced markup and numeric display rules."""

from copy import deepcopy
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from players import utils

pytestmark = pytest.mark.unit


class Cell(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.stack = []
        self.text = []
        self.feed(markup)
        assert self.stack == [], "Unclosed table markup"

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack.pop() == tag, "Misnested table markup"

    def handle_data(self, value):
        self.text.append(value)


@pytest.mark.parametrize(
    "name", ["Ordinary Player", "Zachary L’Heureux", 'A & <img src=x onerror="alert(1)">']
)
def test_name_cell_escapes_text_and_closes_link(name):
    link = '//testserver/player/name/42?label="quoted"&season=20262027'
    cell = Cell(utils.make_name_link(name, link))
    assert cell.tags == [("td", {"class": "name"}), ("a", {"class": "name", "href": link})]
    assert "".join(cell.text) == name


@pytest.mark.parametrize(
    "value, tip", [(0, 'Zero & "nothing"'), ("<b>BUF</b>", '<script>alert("tip")</script>')]
)
def test_tooltip_cell_preserves_literal_text(value, tip):
    cell = Cell(utils.make_tooltip(value, tip))
    assert [tag for tag, attrs in cell.tags] == ["td", "span"]
    assert cell.tags[0][1] == {"class": "cell-with-tooltip"}
    assert "".join(cell.text) == str(value) + tip


def request():
    return SimpleNamespace(user=SimpleNamespace(is_authenticated=False, username=""))


def test_player_json_identity_tooltips_and_missing_metadata():
    fields = {
        "slug": "literal-player",
        "nhl_id": 42,
        "name": '<b>A & "B"</b>',
        "team": ["B&F", '<img src=x onerror="team()">'],
        "nation_abbr": "C&N",
        "nation": "<script>nation()</script>",
        "draft_number": None,
        "draft_year": None,
        "goals": 0,
        "hits": None,
    }
    columns = [
        "number",
        "name",
        "team",
        "nation_abbr",
        "draft_number",
        "draft_year",
        "goals",
        "hits",
    ]
    second = dict(fields, team=None)
    result = utils.process_json(
        request(), columns, "testserver", [{"fields": fields}, {"fields": second}], 100, 25
    )
    assert result["total"] == 100
    first, last = result["rows"]
    assert [first[0], last[0]] == [26, 27]
    assert Cell(first[1]).tags[1][1]["href"] == "//testserver/player/literal-player/42"
    assert "".join(Cell(first[1]).text) == '<b>A & "B"</b>'
    assert "".join(Cell(first[2]).text) == 'B&F<img src=x onerror="team()">'
    assert "".join(Cell(first[3]).text) == "C&N<script>nation()</script>"
    assert "".join(Cell(last[2]).text) == "—No team"
    for row in result["rows"]:
        assert ["".join(Cell(cell).text) for cell in row[4:6]] == ["—Undrafted", "—Undrafted"]
        assert row[6:] == [0, "—"]


@pytest.mark.parametrize(
    "gaa, percentage, expected",
    [(2.345, 0.91234, ["2.35", "0.912"]), (0, 0, ["0.00", "0.000"]), (None, None, ["—", "—"])],
)
def test_goalie_json_precision_and_missing_values(gaa, percentage, expected):
    fields = {"slug": "goalie", "nhl_id": 42, "goals_against_av": gaa, "saves_perc": percentage}
    result = utils.process_json(
        request(), ["goals_against_av", "saves_perc"], "testserver", [{"fields": fields}], 1, 0
    )
    assert result == {"total": 1, "rows": [expected]}


@pytest.mark.parametrize(
    "percentage, expected", [(0.91234, "0.912"), (0, "0.000"), (None, "—"), ("missing", "—")]
)
def test_gamelog_precision_missing_values_and_escaped_cells(percentage, expected):
    game = {
        "player": {"name": "<b>Literal & Player</b>", "slug": "literal-player", "nhl_id": 42},
        "team": {"abbr": "B&F", "name": '<img src=x onerror="team()">'},
        "opponent": {"abbr": "O&P", "name": "Other & Team"},
        "goalsAgainst": 0,
    }
    if percentage != "missing":
        game["savePercentage"] = percentage
    before = deepcopy(game)
    columns = [
        "player.name",
        "team.abbr",
        "opponent.abbr",
        "goalsAgainst",
        "savePercentage",
        "saves",
    ]
    result = utils.process_json_gamelog(columns, "testserver", [game], 12)
    assert result["total"] == 12
    row = result["rows"][0]
    assert "".join(Cell(row[0]).text) == game["player"]["name"]
    assert "".join(Cell(row[1]).text) == 'B&F<img src=x onerror="team()">'
    assert "".join(Cell(row[2]).text) == "O&POther & Team"
    assert row[3:] == [0, expected, "—"]
    assert game == before
