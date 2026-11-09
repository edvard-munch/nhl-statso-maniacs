"""Browser polling reads saved game data without loaders or database writes."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
import pytest

from players.models import Game, Goalie, Skater
from players.tests.integration.tests_game_pages_db import game_page  # noqa: F401
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def endpoint(game):
    return reverse("ajax_game", args=[game.slug, game.nhl_id])


def snapshot():
    return {model: list(model.objects.order_by("pk").values()) for model in (Game, Skater, Goalie)}


def test_game_refresh_is_private_read_only_and_uses_saved_game_rows(
    client, game_page, requests_mock
):
    before = snapshot()
    calls = requests_mock.call_count
    response = client.get(endpoint(game_page.game))
    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"] and "private" in response["Cache-Control"]
    data = response.json()
    assert data["entity"] == f"game:{game_page.game.nhl_id}"
    assert set(data["tables"]) == {
        "away_fwds",
        "away_d_men",
        "home_fwds",
        "home_d_men",
        "away_goalies",
        "home_goalies",
    }
    assert "01:01" in data["tables"]["away_fwds"]
    assert "09:59" not in data["tables"]["away_fwds"]
    assert "24/26" in data["tables"]["away_goalies"]
    assert data["freshness"]["saved_at"] == game_page.game.updated_date.isoformat()
    assert snapshot() == before
    assert requests_mock.call_count == calls


@pytest.mark.parametrize("final", [False, True])
def test_old_unfinished_data_is_stale_but_old_finals_are_not(client, game_page, final):
    saved = timezone.now() - timedelta(hours=1)
    Game.objects.filter(pk=game_page.game.pk).update(game_finished=final, updated_date=saved)
    data = client.get(endpoint(game_page.game)).json()["freshness"]
    assert data["final"] is final
    assert ("Data may be out of date" in data["text"]) is (not final)
    assert data["saved_at"] == saved.isoformat()
    again = client.get(endpoint(game_page.game)).json()["freshness"]
    assert again["saved_at"] == data["saved_at"]
    assert again["checked_at"] >= data["checked_at"]


def test_missing_supplementary_values_warn_instead_of_claiming_complete(client, game_page):
    player = game_page.players["away_forward"]
    player.gamelog_stats[game_page.day["date"]]["powerPlayToi"] = None
    player.save()
    data = client.get(endpoint(game_page.game)).json()
    assert data["freshness"]["partial"] is True
    assert "unavailable" in data["freshness"]["text"]
    assert "—" in data["tables"]["away_fwds"]


def test_refresh_favorite_buttons_are_viewer_specific(client, game_page):
    public = client.get(endpoint(game_page.game)).json()
    assert 'class="js-fav-add"' in public["tables"]["away_fwds"]
    client.force_login(game_page.user)
    private = client.get(endpoint(game_page.game)).json()
    assert 'class="js-fav-del"' in private["tables"]["away_fwds"]


def test_refresh_rejects_mutations_and_wrong_game_slug(client, game_page):
    before = snapshot()
    assert client.post(endpoint(game_page.game)).status_code == 405
    assert (
        client.get(reverse("ajax_game", args=["wrong-slug", game_page.game.nhl_id])).status_code
        == 404
    )
    assert snapshot() == before


def test_scoreboard_refresh_stays_on_requested_day_and_handles_empty_day(client, game_page):
    url = reverse("ajax_scoreboard", args=[game_page.day["date"]])
    before = snapshot()
    response = client.get(url)
    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    assert response.json()["entity"] == "scoreboard:" + game_page.day["date"]
    assert game_page.game.result in response.json()["games"]
    empty = client.get(reverse("ajax_scoreboard", args=["2000-01-01"])).json()
    assert not empty["freshness"]["has_data"]
    assert "No saved games" in empty["games"]
    assert client.get(reverse("ajax_scoreboard", args=["bad-date"])).status_code == 404
    assert client.post(url).status_code == 405
    assert snapshot() == before


def test_scoreboard_escapes_result_and_observes_separately_saved_updates(client, game_page):
    url = reverse("ajax_scoreboard", args=[game_page.day["date"]])
    Game.objects.filter(pk=game_page.game.pk).update(result="<script>bad()</script>")
    data = client.get(url).json()
    assert "<script>" not in data["games"]
    assert "&lt;script&gt;" in data["games"]
