"""Injected transport failures must preserve UI state and recover on explicit retry."""

from django.contrib.auth.models import User
from django.urls import reverse
import pytest

from players.models import Goalie, Skater, Team
from players.tests.browser.tests_saved_lists_browser import memberships
from players.tests.integration.tests_team_season_tables import team_players  # noqa: F401

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("scenario", ["favorite-recovery", "comparison-recovery"])
def test_saved_ajax_failure_recovery(scenario, browser_players, browser_run, client):
    owner = User.objects.create_user(username="recovery-owner")
    other = User.objects.create_user(username="recovery-other")
    for player in browser_players.values():
        player.favoriting.add(owner, other)
        player.comparing.add(owner, other)
    before_other = memberships(other)
    before_owner = memberships(owner)
    before_players = {model: list(model.objects.values()) for model in (Skater, Goalie)}
    client.force_login(owner)
    route = "favorites" if scenario == "favorite-recovery" else "comparison"
    browser_run("ajax-recovery.mjs", scenario, reverse(route), client=client)
    after = memberships(owner)
    if scenario == "favorite-recovery":
        assert after["favorite_skaters"] == []
        assert after["favorite_goalies"] == before_owner["favorite_goalies"]
        assert after["comparable_skaters"] == before_owner["comparable_skaters"]
        assert after["comparable_goalies"] == before_owner["comparable_goalies"]
    else:
        assert after["comparable_skaters"] == after["comparable_goalies"] == []
        assert after["favorite_skaters"] == before_owner["favorite_skaters"]
        assert after["favorite_goalies"] == before_owner["favorite_goalies"]
    assert memberships(other) == before_other
    assert {model: list(model.objects.values()) for model in (Skater, Goalie)} == before_players


def test_team_ajax_failure_recovery(team_players, browser_run):
    before = {
        model: list(model.objects.order_by("pk").values()) for model in (Team, Skater, Goalie)
    }
    team = team_players["BUF"]
    browser_run(
        "ajax-recovery.mjs", "team-recovery", reverse("team_detail", args=[team.slug, team.nhl_id])
    )
    assert {
        model: list(model.objects.order_by("pk").values()) for model in (Team, Skater, Goalie)
    } == before
