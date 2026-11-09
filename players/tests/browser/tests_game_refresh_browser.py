"""Saved-game polling, failure recovery and stable page state in Chromium."""

from django.urls import reverse
import pytest

from players.models import Game, Goalie, Skater
from players.tests.integration.tests_game_pages_db import game_page  # noqa: F401
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game  # noqa: F401

pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize(
    "scenario", ["game-refresh", "refresh-recovery", "scoreboard-refresh", "refresh-favorite-race"]
)
def test_game_refresh_browser(scenario, game_page, browser_run, client):
    before = {
        model: list(model.objects.order_by("pk").values()) for model in (Game, Skater, Goalie)
    }
    path = (
        reverse("games", args=[game_page.day["date"]])
        if scenario == "scoreboard-refresh"
        else reverse("game_detail", args=[game_page.game.slug, game_page.game.nhl_id])
    )
    client.force_login(game_page.user)
    browser_run("game-refresh.mjs", scenario, path, client=client)
    expected_favorites = 0 if scenario == "refresh-favorite-race" else 1
    assert game_page.user.favorite_skaters.count() == expected_favorites
    assert {
        model: list(model.objects.order_by("pk").values()) for model in (Game, Skater, Goalie)
    } == before
