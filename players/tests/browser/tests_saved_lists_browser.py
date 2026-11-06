"""Authenticated saved-list controls exercise real AJAX and M2M persistence."""

from django.contrib.auth.models import User
from django.urls import reverse
import pytest

from players.models import Goalie, Skater

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


def memberships(user):
    return {
        name: list(getattr(user, name).order_by("pk").values_list("pk", flat=True))
        for name in (
            "favorite_skaters",
            "favorite_goalies",
            "comparable_skaters",
            "comparable_goalies",
        )
    }


@pytest.mark.parametrize(
    "scenario", ["favorites-goalie", "favorites-empty", "favorites-modes", "comparison"]
)
def test_saved_lists_browser(scenario, browser_players, browser_run, client):
    owner = User.objects.create_user(username="browser-owner")
    other = User.objects.create_user(username="browser-other")
    for player in browser_players.values():
        player.favoriting.add(other)
        player.comparing.add(other)
        if scenario != "favorites-empty":
            if scenario != "favorites-goalie" or isinstance(player, Goalie):
                player.favoriting.add(owner)
        if scenario == "comparison":
            player.comparing.add(owner)
    before_other = memberships(other)
    before_owner = memberships(owner)
    before_players = {model: list(model.objects.values()) for model in (Skater, Goalie)}
    client.force_login(owner)
    browser_run(
        "saved-lists-smoke.mjs",
        scenario,
        reverse("comparison" if scenario == "comparison" else "favorites"),
        client=client,
    )
    assert memberships(other) == before_other
    after = memberships(owner)
    if scenario == "comparison":
        assert after["comparable_skaters"] == after["comparable_goalies"] == []
        assert after["favorite_skaters"] == before_owner["favorite_skaters"]
        assert after["favorite_goalies"] == before_owner["favorite_goalies"]
    else:
        assert after == before_owner
    assert {model: list(model.objects.values()) for model in (Skater, Goalie)} == before_players


@pytest.mark.parametrize("kind", ["skater", "goalie"])
@pytest.mark.parametrize("final", [False, True])
def test_favorite_removal_browser(kind, final, browser_players, browser_run, client):
    owner = User.objects.create_user(username="browser-removal-owner")
    other = User.objects.create_user(username="browser-removal-other")
    for key, player in browser_players.items():
        player.favoriting.add(other)
        player.comparing.add(other, owner)
        if not final or key == kind:
            player.favoriting.add(owner)
    before_other = memberships(other)
    before_owner = memberships(owner)
    before_players = {model: list(model.objects.values()) for model in (Skater, Goalie)}
    client.force_login(owner)
    scenario = ("final-" if final else "last-") + kind
    browser_run("favorites-removal.mjs", scenario, reverse("favorites"), client=client)
    after = memberships(owner)
    assert after["favorite_" + ("skaters" if kind == "skater" else "goalies")] == []
    opposite = "favorite_goalies" if kind == "skater" else "favorite_skaters"
    assert after[opposite] == before_owner[opposite]
    assert after["comparable_skaters"] == before_owner["comparable_skaters"]
    assert after["comparable_goalies"] == before_owner["comparable_goalies"]
    assert memberships(other) == before_other
    assert {model: list(model.objects.values()) for model in (Skater, Goalie)} == before_players


def test_saved_mutations_send_post_and_csrf(browser_players, browser_run, client):
    owner = User.objects.create_user(username="post-owner")
    other = User.objects.create_user(username="post-other")
    for player in browser_players.values():
        player.favoriting.add(other)
        player.comparing.add(other)
    before_other = memberships(other)
    before_owner = memberships(owner)
    before_players = {model: list(model.objects.values()) for model in (Skater, Goalie)}
    client.force_login(owner)
    browser_run(
        "saved-mutations-smoke.mjs",
        "post-csrf",
        reverse("players") + "?season=20262027",
        client=client,
    )
    assert memberships(owner) == before_owner
    assert memberships(other) == before_other
    assert {model: list(model.objects.values()) for model in (Skater, Goalie)} == before_players
