"""Real Chromium against Django's live server and a disposable test database."""

from django.urls import reverse
import pytest

from players.models import Goalie, Skater

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("scenario", ["season", "modes", "empty"])
def test_players_browser(scenario, browser_players, browser_run):
    before = {model: list(model.objects.values()) for model in (Skater, Goalie)}
    browser_run("players-smoke.mjs", scenario, reverse("players"))
    assert {model: list(model.objects.values()) for model in (Skater, Goalie)} == before
