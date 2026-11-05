"""Team AJAX controls retain exact season contributions in a real browser."""

from django.urls import reverse
import pytest

from players.models import Goalie, Skater, Team
from players.tests.integration.tests_team_season_tables import team_players  # noqa: F401

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("scenario", ["team-layout", "team-season", "team-empty"])
def test_team_browser(scenario, team_players, browser_run):
    before = {
        model: list(model.objects.order_by("pk").values()) for model in (Team, Skater, Goalie)
    }
    team = team_players["BUF"]
    browser_run("team-smoke.mjs", scenario, reverse("team_detail", args=[team.slug, team.nhl_id]))
    assert {
        model: list(model.objects.order_by("pk").values()) for model in (Team, Skater, Goalie)
    } == before
