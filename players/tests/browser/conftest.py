"""Shared isolated browser fixtures; no optional imports during normal collection."""

from copy import deepcopy
import os
from pathlib import Path
import subprocess

from django.conf import settings
import pytest
import requests

from players.management.commands.upd_pls_tot import get_season_by_season_stats
from players.models import Goalie, Skater, Team

ROOT = Path(__file__).resolve().parents[3]
BROWSER_PROCESS_TIMEOUT = 90


@pytest.fixture
def browser_players(season_stats_data):
    team = Team.objects.create(nhl_id=7, abbr="BUF", name="Browser Buffalo")
    players = {}
    for kind, model, nhl_id, position in (
        ("skater", Skater, 900001, "C"),
        ("goalie", Goalie, 900002, "G"),
    ):
        case = season_stats_data["cases"]["current_" + kind]
        rows = get_season_by_season_stats(deepcopy(case["landing_season_totals"]), position)
        career = (
            {"gamesPlayed": 90, "goals": 22}
            if kind == "skater"
            else {"gamesPlayed": 40, "wins": 20}
        )
        players[kind] = model.objects.create(
            nhl_id=nhl_id,
            name="Browser " + kind.title(),
            last_name=kind,
            team=team,
            birth_date="2000-01-01",
            games=999,
            stats_season_id="20252026",
            position_abbr=position,
            sbs_stats=rows,
            career_stats=career,
            **(
                {"goals": 999, "career_stats_avg": {"gamesPlayed": 90, "goals": 0.24}}
                if kind == "skater"
                else {"wins": 999}
            ),
        )
    return players


@pytest.fixture
def browser_run(live_server, monkeypatch):
    def reject_http(*args, **kwargs):
        raise AssertionError("Browser views must not call external HTTP services")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_http)

    def run(script, scenario, path, client=None):
        env = os.environ.copy()
        env.update(PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".browser-cache/browsers"))
        env.pop("NHL_BROWSER_SESSION", None)
        env.pop("NHL_BROWSER_COOKIE_NAME", None)
        if client is not None:
            env.update(
                NHL_BROWSER_SESSION=client.cookies[settings.SESSION_COOKIE_NAME].value,
                NHL_BROWSER_COOKIE_NAME=settings.SESSION_COOKIE_NAME,
            )
        result = subprocess.run(
            ["node", str(ROOT / "browser" / script), scenario, live_server.url + path],
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=BROWSER_PROCESS_TIMEOUT,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    return run
