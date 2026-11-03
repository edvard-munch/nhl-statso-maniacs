"""Function-scoped records using pytest-django's normal migrated test database."""

from copy import deepcopy
from datetime import date

import pytest
import requests
from django.contrib.auth.models import User

from players import utils
from players.management.commands.upd_pls_tot import get_season_by_season_stats
from players.models import Game, Gameday, Goalie, Side, Skater, Team


@pytest.fixture(autouse=True)
def no_live_http(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("View and lookup tests must not make live HTTP requests")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


@pytest.fixture
def view_data(db, season_stats_data):
    home = Team.objects.create(nhl_id=901, abbr="BUF", name="Fixture Home", image="home.png")
    away = Team.objects.create(nhl_id=902, abbr="COL", name="Fixture Away", image="away.png")
    players = {}
    for key, model, nhl_id, case_name, position in (
        ("skater", Skater, 900001, "current_skater", "C"),
        ("goalie", Goalie, 900002, "current_goalie", "G"),
        ("second_goalie", Goalie, 900003, "current_goalie", "G"),
    ):
        case = season_stats_data["cases"][case_name]
        rows = get_season_by_season_stats(deepcopy(case["landing_season_totals"]), position)
        players[key] = model.objects.create(
            nhl_id=nhl_id,
            name="Fixture " + key.replace("_", " ").title(),
            birth_date="2000-01-01",
            games=4,
            team=home,
            position_abbr=position,
            stats_season_id="20262027",
            sbs_stats=rows,
            career_stats={},
        )
    day = Gameday.objects.create(day=date(2026, 10, 1))
    game = Game.objects.create(
        nhl_id=900004, slug="fixture-away-home", gameday=day, result="COL 1 - 2 BUF"
    )
    Side.objects.create(nhl_side_id=900005, game=game, team=home, side="home")
    Side.objects.create(nhl_side_id=900006, game=game, team=away, side="away")
    game.home_forwards.add(players["skater"])
    game.home_goalies.add(players["goalie"])
    for key in ("skater", "goalie"):
        player = players[key]
        columns = (
            utils.COLUMNS_GOALIES_GAMELOG if key == "goalie" else utils.COLUMNS_SKATERS_GAMELOG
        )
        log = {field: 0 for field in columns if "." not in field}
        log.update(
            format_date="Oct 01",
            player={"name": player.name, "slug": player.slug, "nhl_id": player.nhl_id},
            team={"abbr": home.abbr, "name": home.name},
            opponent={"abbr": away.abbr, "name": away.name},
            savePercentage=0.95,
            timeOnIce="20:00",
            powerPlayTimeOnIce="01:00",
            shortHandedTimeOnIce="00:00",
        )
        player.gamelog_stats = {str(day.day): log}
        player.save(update_fields=["gamelog_stats"])
    user = User.objects.create_user(username="fixture-view-user")
    user.favorite_skaters.add(players["skater"])
    user.favorite_goalies.add(players["goalie"])
    user.comparable_skaters.add(players["skater"])
    user.comparable_goalies.add(players["goalie"])
    return dict(players, home=home, away=away, day=day, game=game, user=user)
