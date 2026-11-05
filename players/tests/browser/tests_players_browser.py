"""Real Chromium against Django's live server and a disposable test database."""

import os
from pathlib import Path
import subprocess

import requests
from django.urls import reverse
import pytest

from players.management.commands.upd_pls_tot import get_season_by_season_stats
from players.models import Goalie, Skater, Team
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[3]
BROWSER_PROCESS_TIMEOUT = 90
pytestmark = [pytest.mark.browser, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("scenario", ["season", "modes", "empty"])
def test_players_browser(scenario, live_server, season_stats_data, monkeypatch):
    def reject_http(*args, **kwargs):
        raise AssertionError("Browser views must not call external HTTP services")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_http)
    team = Team.objects.create(nhl_id=7, abbr="BUF", name="Browser Buffalo")
    for kind, model, nhl_id, position in (
        ("skater", Skater, 900001, "C"),
        ("goalie", Goalie, 900002, "G"),
    ):
        case = season_stats_data["cases"]["current_" + kind]
        rows = get_season_by_season_stats(deepcopy(case["landing_season_totals"]), position)
        model.objects.create(
            nhl_id=nhl_id,
            name="Browser " + kind.title(),
            last_name=kind,
            team=team,
            birth_date="2000-01-01",
            games=999,
            stats_season_id="20252026",
            position_abbr=position,
            sbs_stats=rows,
            career_stats={},
            **({"goals": 999} if kind == "skater" else {"wins": 999}),
        )
    before = {model: list(model.objects.values()) for model in (Skater, Goalie)}
    env = os.environ.copy()
    env.update(PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".browser-cache/browsers"))
    result = subprocess.run(
        [
            "node",
            str(ROOT / "browser/players-smoke.mjs"),
            scenario,
            live_server.url + reverse("players"),
        ],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=BROWSER_PROCESS_TIMEOUT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {model: list(model.objects.values()) for model in (Skater, Goalie)} == before
