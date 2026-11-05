"""Search results and autocomplete contracts from shared isolated view records."""

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
import pytest

from players import utils
from players.tests.unit.tests_readonly_db.conftest import no_live_http, view_data  # noqa: F401


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class Label(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.attrs = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append(dict(attrs))

    def handle_data(self, data):
        self.text.append(data)


@pytest.fixture
def search_data(view_data):
    for key, name in [
        ("skater", "Needle Skater"),
        ("goalie", "Needle Goalie"),
        ("home", "Needle Team"),
    ]:
        view_data[key].name = name
        view_data[key].save(update_fields=["name"])
    return view_data


def autocomplete(client, term=None):
    return client.get("/ajax_calls/search/", {} if term is None else {"term": term})


@pytest.mark.parametrize("term", ["needle", "  NeEdLe  "])
def test_search_returns_only_matching_players_and_teams_with_links(client, search_data, term):
    response = client.get(reverse("search"), {"q": term})
    assert response.status_code == 200
    assert response.context["query"] == term.strip()
    assert {p.pk for p in response.context["players"]} == {
        search_data["skater"].pk,
        search_data["goalie"].pk,
    }
    assert list(response.context["teams"]) == [search_data["home"]]
    html = response.content.decode()
    for key, route in [
        ("skater", "player_detail"),
        ("goalie", "player_detail"),
        ("home", "team_detail"),
    ]:
        obj = search_data[key]
        assert reverse(route, args=[obj.slug, obj.nhl_id]) in html
        assert obj.name in html
    assert search_data["second_goalie"].name not in html


@pytest.mark.parametrize("term", [None, "", "   ", "\t\n"])
def test_blank_search_requests_a_term_without_reading_records(client, search_data, term):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("search"), {} if term is None else {"q": term})
    assert response.status_code == 200
    assert response.content == b"Please submit a search term."
    assert len(queries) == 0


@pytest.mark.parametrize("term", [None, "", "   ", "\t\n"])
def test_blank_autocomplete_has_no_suggestions_or_database_reads(client, search_data, term):
    with CaptureQueriesContext(connection) as queries:
        response = autocomplete(client, term)
    assert response.status_code == 200
    assert response.json() == {}
    assert len(queries) == 0


def test_no_matches_have_an_explicit_empty_search_state(client, search_data):
    response = client.get(reverse("search"), {"q": "no-such-fixture"})
    assert response.context["players"] == []
    assert list(response.context["teams"]) == []
    assert b"No players matched your search criteria." in response.content
    assert autocomplete(client, "no-such-fixture").json() == {}


@pytest.mark.parametrize("term", ["%", "_", "Émile"])
def test_search_and_autocomplete_treat_terms_as_literal_substrings(client, search_data, term):
    player = search_data["skater"]
    player.name = "Literal " + term + " Player"
    player.save(update_fields=["name"])
    result = client.get(reverse("search"), {"q": term})
    assert result.context["players"] == [player]
    suggestions = autocomplete(client, term).json()
    assert [
        r["value"]
        for r in suggestions.values()
        if r.get("value") != utils.SEARCH_RES_FULL and "value" in r
    ] == [player.name]


@pytest.mark.parametrize("group", ["both", "players", "teams"])
def test_autocomplete_grouping_and_canonical_links(client, search_data, group):
    term = "Needle" if group == "both" else "Skater" if group == "players" else "Team"
    response = autocomplete(client, "  " + term + "  ")
    assert response.status_code == 200
    rows = list(response.json().values())
    values = [r.get("value") for r in rows if "value" in r]
    expected = (
        ["Needle Skater", "Needle Goalie", "Needle Team"]
        if group == "both"
        else ["Needle Skater"]
        if group == "players"
        else ["Needle Team"]
    )
    assert values == expected + [utils.SEARCH_RES_FULL]
    assert sum(r["label"] == utils.SEARCH_RES_DELIMETER for r in rows) == (
        2 if group == "both" else 1
    )
    for row in rows:
        if "value" not in row:
            continue
        label = Label(row["label"])
        assert label.tags == ["a"]
        target = label.attrs[0]["href"]
        if row["value"] == utils.SEARCH_RES_FULL:
            assert urlsplit(target).path == reverse("search")
            assert parse_qs(urlsplit(target).query) == {"q": [term]}
        else:
            obj = next(
                search_data[k]
                for k in ("skater", "goalie", "home")
                if search_data[k].name == row["value"]
            )
            route = "team_detail" if row["value"] == "Needle Team" else "player_detail"
            assert urlsplit(target).path == reverse(route, args=[obj.slug, obj.nhl_id])


@pytest.mark.parametrize("term", ['A&B # + ? "', '<img src=x onerror="alert(1)">'])
def test_autocomplete_escapes_label_text_and_encodes_full_results_query(client, search_data, term):
    for key in ("skater", "goalie", "home"):
        obj = search_data[key]
        obj.name = term + " Fixture"
        obj.save(update_fields=["name"])
    result = autocomplete(client, term).json()
    assert len(result) == 6
    for row in result.values():
        if "value" not in row:
            continue
        label = Label(row["label"])
        assert label.tags == ["a"]
        assert set(label.attrs[0]) == {"class", "href"}
        if row["value"] == utils.SEARCH_RES_FULL:
            target = urlsplit(label.attrs[0]["href"])
            assert parse_qs(target.query) == {"q": [term]}
            assert target.fragment == ""
        else:
            assert "".join(label.text) == term + " Fixture"
    response = client.get(reverse("search"), {"q": term})
    if term.startswith("<"):
        assert term.encode() not in response.content
        assert b"&lt;img" in response.content


@pytest.mark.parametrize("viewer", ["anonymous", "owner", "other"])
def test_search_saved_controls_follow_viewer_membership(client, search_data, viewer):
    owner = search_data["user"]
    if viewer == "owner":
        client.force_login(owner)
    elif viewer == "other":
        other = User.objects.create_user(username="other-search-viewer")
        other.favorite_goalies.add(search_data["goalie"])
        client.force_login(other)
    response = client.get(reverse("search"), {"q": "Needle"})
    html = response.content.decode()
    for key in ("skater", "goalie"):
        player = search_data[key]
        url = reverse("player_favorite", args=[player.slug, player.nhl_id])
        favorite = viewer == "owner" or (viewer == "other" and key == "goalie")
        css = "js-fav-del" if favorite else "js-fav-add"
        assert f'class="{css}" href="{url}"' in html
        url = reverse("player_compare", args=[player.slug, player.nhl_id])
        css = (
            "button act-button js-compare-del"
            if viewer == "owner"
            else "button sm-button js-compare-add"
        )
        assert f'class="{css}" href="{url}"' in html
    assert list(owner.favorite_skaters.all()) == [search_data["skater"]]
