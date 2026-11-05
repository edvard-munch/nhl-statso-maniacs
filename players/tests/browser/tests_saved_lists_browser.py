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
