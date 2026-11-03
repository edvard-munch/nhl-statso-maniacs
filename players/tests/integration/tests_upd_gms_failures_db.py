"""A required-response failure must not publish half a day's game refresh."""

import pytest
from django.core.management.base import CommandError

from players.management.commands import upd_gms
from players.models import Game, Gameday, Side, Team


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def game_day(monkeypatch, requests_mock):
    monkeypatch.setattr(upd_gms, "sleep", lambda delay: None)
    for nhl_id, abbr in [(1, "NJD"), (7, "BUF"), (16, "COL"), (52, "WPG")]:
        Team.objects.create(nhl_id=nhl_id, abbr=abbr, name="Fixture " + abbr)
    day = {"date": "2026-11-21", "games": [{"id": 2026020001}, {"id": 2026020002}]}
    first = {"gameState": "FUT", "awayTeam": {"id": 1}, "homeTeam": {"id": 7}}
    second = {"gameState": "FUT", "awayTeam": {"id": 16}, "homeTeam": {"id": 52}}
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020001), json=first)
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020002), text="<html>Unavailable</html>")
    return day, first, second


def test_later_boxscore_failure_rolls_back_new_day_and_preserves_prior_days(game_day):
    day, _, _ = game_day
    earlier = Gameday.objects.create(day="2026-11-20", all_games_uploaded=True)
    previous = Game.objects.create(nhl_id=2026020000, gameday=earlier, result="Previously loaded")
    with pytest.raises(CommandError) as error:
        upd_gms.process_games(day, None)
    assert "Gameday 2026-11-21" in str(error.value)
    assert "2026020002" in str(error.value)
    assert not Gameday.objects.filter(day=day["date"]).exists()
    assert list(Game.objects.values_list("pk", flat=True)) == [previous.pk]
    assert Side.objects.count() == 0
    earlier.refresh_from_db()
    assert earlier.all_games_uploaded is True


def test_failed_existing_refresh_is_unchanged_and_can_be_replayed(game_day, requests_mock):
    day, _, second = game_day
    stored = Gameday.objects.create(day=day["date"])
    game = Game.objects.create(
        nhl_id=2026020001, gameday=stored, slug="existing-slug", result="Keep existing result"
    )
    with pytest.raises(CommandError):
        upd_gms.process_games(day, None)
    game.refresh_from_db()
    stored.refresh_from_db()
    assert game.result == "Keep existing result"
    assert stored.all_games_uploaded is stored.all_games_finished is False
    assert Side.objects.count() == 0

    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020002), json=second)
    for _ in range(2):
        upd_gms.process_games(day, None)
        assert Game.objects.count() == 2
        assert Side.objects.count() == 4
    game.refresh_from_db()
    stored.refresh_from_db()
    assert game.slug == "existing-slug"
    assert stored.all_games_uploaded is True
    assert stored.all_games_finished is False


@pytest.mark.parametrize("template", [upd_gms.URL_RIGHT_RAIL, upd_gms.URL_PLAY_BY_PLAY])
def test_supplemental_failure_rolls_back_game_refresh(game_day, requests_mock, template):
    day, first, _ = game_day
    first["gameState"] = "LIVE"
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020001), json=first)
    if template == upd_gms.URL_PLAY_BY_PLAY:
        requests_mock.get(upd_gms.URL_RIGHT_RAIL.format(2026020001), json={})
    requests_mock.get(template.format(2026020001), text="<html>Unavailable</html>")
    with pytest.raises(CommandError, match="Gameday 2026-11-21"):
        upd_gms.process_games(day, None)
    assert Game.objects.count() == Gameday.objects.count() == Side.objects.count() == 0
