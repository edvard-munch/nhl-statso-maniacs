"""Visible rows must not determine whether the full favorites list is empty."""

from copy import deepcopy

from django.contrib.auth.models import User
from django.urls import reverse
import pytest

from players.models import Goalie, Skater
from players.tests.browser.tests_saved_lists_browser import memberships

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("kind", ["skater", "goalie"])
@pytest.mark.parametrize("scenario", ["filtered", "paged"])
def test_favorites_filtered_paged_removal(kind, scenario, browser_players, browser_run, client):
    owner = User.objects.create_user(username="paging-owner")
    other = User.objects.create_user(username="paging-other")
    source = browser_players[kind]
    model = type(source)
    players = []
    for index in range(26):
        players.append(
            model.objects.create(
                nhl_id=910000 + index,
                name=f"Saved {kind.title()} {index:02}",
                last_name=f"Saved {index:02}",
                team=source.team,
                birth_date="2000-01-01",
                position_abbr=source.position_abbr,
                sbs_stats=deepcopy(source.sbs_stats),
                stats_season_id="20252026",
                games=999,
                **({"goals": 999} if kind == "skater" else {"wins": 999}),
            )
        )
    opposite = browser_players["goalie" if kind == "skater" else "skater"]
    for player in [*players, opposite]:
        player.favoriting.add(owner, other)
        player.comparing.add(owner, other)
    before_other = memberships(other)
    before_owner = memberships(owner)
    before_players = {cls: list(cls.objects.order_by("pk").values()) for cls in (Skater, Goalie)}
    client.force_login(owner)
    browser_run("favorites-paging.mjs", f"{scenario}-{kind}", reverse("favorites"), client=client)
    expected = dict(before_owner)
    field = "favorite_skaters" if kind == "skater" else "favorite_goalies"
    expected[field] = [pk for pk in expected[field] if pk != players[-1].pk]
    assert memberships(owner) == expected
    assert memberships(other) == before_other
    assert {
        cls: list(cls.objects.order_by("pk").values()) for cls in (Skater, Goalie)
    } == before_players
