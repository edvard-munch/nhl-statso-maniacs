"""Explicit game/date selection through mocked HTTP and real game publication."""

from copy import deepcopy
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
import pytest

from players.management.commands import upd_gms
from players.models import Game, Gameday, Side
from players.tests.integration.tests_upd_gms_rosters_db import (
    loaded_game as loaded_game,
    load,
    log_for,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def target(loaded_game):
    fixture = loaded_game
    fixture.payload["gameDate"] = fixture.day["date"]
    fixture.payload["gameScheduleState"] = "OK"
    fixture.register()
    return fixture


def run(*args):
    output = StringIO()
    call_command("upd_gms", *args, stdout=output)
    return output.getvalue()


def schedule(requests_mock, target, games=None, date=None, extra_days=()):
    date = date or target.day["date"]
    games = (
        games
        if games is not None
        else [{"id": target.payload["id"], "gameState": target.payload["gameState"]}]
    )
    requests_mock.get(
        upd_gms.URL_SCHEDULE.format(date),
        json={
            "gameWeek": [{"date": date, "games": games}, *extra_days],
            "nextStartDate": "2026-12-01",
        },
    )


@pytest.mark.parametrize(
    "args",
    [
        ("--date", "2026-2-03"),
        ("--date", "2026-02-30"),
        ("--date", "not-a-date"),
        ("--game-id", "2026030001"),
        ("--game-id", "202602001"),
        ("--game-id", "x"),
        ("--state", "active"),
    ],
)
def test_invalid_selection_fails_before_requests_or_writes(requests_mock, args):
    with pytest.raises(CommandError):
        run(*args)
    assert not requests_mock.called
    assert Game.objects.count() == Gameday.objects.count() == 0


def test_date_targets_only_exact_day_and_skips_unstarted_and_other_game_types(
    target, requests_mock
):
    schedule(
        requests_mock,
        target,
        games=[
            {"id": target.payload["id"], "gameState": "OFF"},
            {"id": 2026020002, "gameState": "FUT"},
            {"id": 2026020003, "gameState": "PRE"},
            {"id": 2026020004, "gameState": "LIVE", "gameScheduleState": "PPD"},
            {"id": 2026030001, "gameState": "OFF"},
        ],
        extra_days=[{"date": "2026-11-22", "games": [{"id": 2026020005, "gameState": "OFF"}]}],
    )
    output = run("--date", target.day["date"])
    assert "1 refreshed, 3 deferred" in output
    assert "not regular season" in output
    assert list(Game.objects.values_list("nhl_id", flat=True)) == [target.payload["id"]]
    day = Gameday.objects.get()
    assert day.all_games_finished is day.all_games_uploaded is False
    requested = [request.url for request in requests_mock.request_history]
    assert not any(
        "2026020002" in url or "2026020003" in url or "2026020004" in url or "2026020005" in url
        for url in requested
    )
    assert sum("/schedule/" in url for url in requested) == 1


@pytest.mark.parametrize("kind", ["date", "game-id"])
def test_targets_deduplicate_and_replay_finished_games(target, requests_mock, kind):
    if kind == "date":
        schedule(requests_mock, target)
    value = target.day["date"] if kind == "date" else str(target.payload["id"])
    for goals in (1, 4):
        target.payload["playerByGameStats"]["awayTeam"]["forwards"][0]["goals"] = goals
        target.register()
        before = len(requests_mock.request_history)
        output = run("--" + kind, value, "--" + kind, value)
        assert "1 refreshed, 0 deferred" in output
        assert (
            sum(
                request.url == upd_gms.URL_BOXSCORE.format(target.payload["id"])
                for request in requests_mock.request_history[before:]
            )
            == 1
        )
        assert log_for(target, "away_forward")["goals"] == goals
        assert Game.objects.get().game_finished is True
        assert (Game.objects.count(), Gameday.objects.count(), Side.objects.count()) == (1, 1, 2)
        assert target.user.favorite_skaters.count() == target.user.comparable_skaters.count() == 1
    day = Gameday.objects.get()
    assert day.all_games_uploaded is (kind == "date")
    assert day.all_games_finished is (kind == "date")


@pytest.mark.parametrize(
    "state,game_state,expected",
    [
        ("active", "LIVE", True),
        ("active", "CRIT", True),
        ("active", "OFF", False),
        ("active", "OVER", False),
        ("final", "OVER", False),
        ("final", "FINAL", True),
        ("final", "OFF", True),
        ("started", "OVER", True),
        ("started", "PRE", False),
        ("started", "FUT", False),
    ],
)
def test_state_filter_rechecks_authoritative_boxscore(
    target, requests_mock, state, game_state, expected
):
    target.payload["gameState"] = game_state
    target.register()
    output = run("--game-id", str(target.payload["id"]), "--state", state)
    assert (Game.objects.count() == 1) is expected
    assert ("1 refreshed" in output) is expected
    if not expected:
        assert len(requests_mock.request_history) == 1
        assert Gameday.objects.count() == 0


def test_date_filter_does_not_promote_whole_day_and_can_clear_stale_completion(
    target, requests_mock
):
    game = load(target)
    schedule(
        requests_mock,
        target,
        games=[
            {"id": game.nhl_id, "gameState": "OFF"},
            {"id": 2026020002, "gameState": "LIVE"},
        ],
    )
    run("--date", target.day["date"], "--state", "final")
    day = Gameday.objects.get()
    assert day.all_games_finished is day.all_games_uploaded is False
    assert Game.objects.count() == 1


@pytest.mark.parametrize("state", ["FUT", "PRE"])
def test_direct_pregame_payload_without_teams_is_deferred(requests_mock, state):
    requests_mock.get(
        upd_gms.URL_BOXSCORE.format(2026020001),
        json={"id": 2026020001, "gameDate": "2026-11-21", "gameState": state},
    )
    assert "0 refreshed, 1 deferred" in run("--game-id", "2026020001")
    assert len(requests_mock.request_history) == 1
    assert Game.objects.count() == Gameday.objects.count() == 0


@pytest.mark.parametrize("case", ["missing", "duplicate", "malformed", "invalid-state"])
def test_bad_target_schedule_is_not_an_empty_success(target, requests_mock, case):
    day = {"date": target.day["date"], "games": [{"id": target.payload["id"], "gameState": "OFF"}]}
    week = [day]
    if case == "missing":
        week = []
    elif case == "duplicate":
        day["games"] *= 2
    elif case == "malformed":
        day["games"] = None
    else:
        day["games"][0]["gameState"] = {"bad": "state"}
    requests_mock.get(upd_gms.URL_SCHEDULE.format(target.day["date"]), json={"gameWeek": week})
    with pytest.raises(CommandError):
        run("--date", target.day["date"])
    assert Game.objects.count() == Gameday.objects.count() == 0
    assert len(requests_mock.request_history) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 2026020002),
        ("gameDate", "2026-11-22"),
        ("gameDate", "bad"),
        ("gameState", "bad"),
        ("awayTeam", None),
    ],
)
def test_bad_boxscore_identity_or_shape_preserves_existing_game(
    target, requests_mock, field, value
):
    load(target)
    before = {
        "game": list(Game.objects.values()),
        "logs": deepcopy(log_for(target, "away_forward")),
    }
    schedule(requests_mock, target)
    target.payload[field] = value
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020001), json=target.payload)
    with pytest.raises(CommandError):
        run("--date", target.day["date"])
    assert list(Game.objects.values()) == before["game"]
    assert log_for(target, "away_forward") == before["logs"]


def test_game_date_is_from_payload_not_utc_today(target):
    target.payload["gameDate"] = "2026-03-08"
    target.register()
    run("--game-id", str(target.payload["id"]))
    assert str(Game.objects.get().gameday.day) == "2026-03-08"
    player = target.players["away_forward"]
    player.refresh_from_db()
    assert set(player.gamelog_stats) == {"2025-10-01", "2026-03-08"}


def test_saved_date_change_is_rejected_instead_of_guessing_history(target):
    load(target)
    target.payload["gameDate"] = "2026-11-22"
    target.register()
    with pytest.raises(CommandError, match="saved date differs"):
        run("--game-id", str(target.payload["id"]))
    assert str(Game.objects.get().gameday.day) == target.day["date"]
    assert Gameday.objects.count() == 1


def empty_reports(requests_mock, target):
    requests_mock.get(upd_gms.URL_RIGHT_RAIL.format(target.payload["id"]), json={})
    requests_mock.get(upd_gms.URL_PLAY_BY_PLAY.format(target.payload["id"]), json={})


def test_missing_reports_preserve_same_game_values_but_fresh_zero_wins(target, requests_mock):
    load(target)
    before = deepcopy(log_for(target, "away_forward"))
    empty_reports(requests_mock, target)
    forward = target.payload["playerByGameStats"]["awayTeam"]["forwards"][0]
    forward.update(goals=5, powerPlayPoints=0, powerPlayToi="00:00")
    target.register()
    run("--game-id", str(target.payload["id"]))
    after = log_for(target, "away_forward")
    assert (after["goals"], after["powerPlayPoints"], after["powerPlayToi"]) == (5, 0, "00:00")
    for field in ("faceoffs", "shPoints", "shorthandedToi"):
        assert after[field] == before[field]
    assert set(target.players["away_forward"].gamelog_stats) == {"2025-10-01", target.day["date"]}


def test_new_missing_report_fields_are_unknown_and_later_reports_fill_them(target, requests_mock):
    empty_reports(requests_mock, target)
    run("--game-id", str(target.payload["id"]))
    row = log_for(target, "away_forward")
    assert all(row[field] is None for field in upd_gms.REPORT_STAT_KEYS)
    assert row["goals"] == 1
    # Restore only a TOI report; known zero remains a real value, not a missing one.
    requests_mock.get(
        upd_gms.URL_RIGHT_RAIL.format(target.payload["id"]),
        json={"gameReports": {"toiAway": "https://reports.invalid/toiAway"}},
    )
    target.register()
    run("--game-id", str(target.payload["id"]))
    assert log_for(target, "away_forward")["powerPlayToi"] == "04:31"
    assert log_for(target, "away_forward")["faceoffs"] is None


@pytest.mark.parametrize("report", [upd_gms.URL_RIGHT_RAIL, upd_gms.URL_PLAY_BY_PLAY])
def test_required_report_failure_preserves_existing_publication(target, requests_mock, report):
    load(target)
    before_game = list(Game.objects.values())
    before_log = deepcopy(log_for(target, "away_forward"))
    target.payload["awayTeam"]["score"] = 5
    target.register()
    requests_mock.get(report.format(target.payload["id"]), text="<html>Unavailable</html>")
    with pytest.raises(CommandError):
        run("--game-id", str(target.payload["id"]))
    assert list(Game.objects.values()) == before_game
    assert log_for(target, "away_forward") == before_log


def test_later_target_failure_keeps_earlier_committed_game(target, requests_mock):
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020002), status_code=404)
    with pytest.raises(CommandError, match="2026020002"):
        run("--game-id", str(target.payload["id"]), "--game-id", "2026020002")
    assert Game.objects.get().nhl_id == target.payload["id"]
    assert log_for(target, "away_forward")["goals"] == 1


def test_publication_failure_rolls_back_day_game_and_player_writes(target):
    player = target.players["home_forward"]
    player.gamelog_stats[target.day["date"]] = {
        "gameId": 2026020999,
        "player": {"nhl_id": player.nhl_id},
        "goals": 9,
    }
    player.save(update_fields=["gamelog_stats"])
    before = deepcopy(target.players["away_forward"].gamelog_stats)
    with pytest.raises(CommandError, match="Unverified same-date gamelog"):
        run("--game-id", str(target.payload["id"]))
    assert Game.objects.count() == Gameday.objects.count() == Side.objects.count() == 0
    target.players["away_forward"].refresh_from_db()
    assert target.players["away_forward"].gamelog_stats == before
    player.refresh_from_db()
    assert player.gamelog_stats[target.day["date"]]["goals"] == 9


@pytest.mark.parametrize("route", ["game_detail", "player_gamelog", "player_detail"])
def test_unknown_report_values_render_as_dashes_on_game_and_player_pages(
    target, requests_mock, client, route
):
    from django.urls import reverse

    empty_reports(requests_mock, target)
    run("--game-id", str(target.payload["id"]))
    for player in target.players.values():
        player.image = "fixtures/player.png"
        player.age = 25
        player.save(update_fields=["image", "age"])
    game = Game.objects.get()
    player = target.players["away_forward"]
    obj = game if route == "game_detail" else player
    response = client.get(reverse(route, args=[obj.slug, obj.nhl_id]))
    assert response.status_code == 200
    html = response.content.decode()
    assert html.count("<td>—</td>") >= 5
    assert ">None<" not in html


def test_multiple_dates_are_finite_and_empty_date_succeeds(target, requests_mock):
    schedule(requests_mock, target)
    schedule(requests_mock, target, date="2026-11-22", games=[])
    output = run("--date", target.day["date"], "--date", "2026-11-22")
    assert "Target date 2026-11-22: 0 scheduled game(s)" in output
    assert "1 refreshed, 0 deferred" in output
    assert sum("/schedule/" in request.url for request in requests_mock.request_history) == 2
    assert Gameday.objects.count() == 1


def test_date_active_filter_skips_other_states_without_fetching(target, requests_mock):
    target.payload["gameState"] = "CRIT"
    target.register()
    schedule(
        requests_mock,
        target,
        games=[
            {"id": target.payload["id"], "gameState": "CRIT"},
            {"id": 2026020002, "gameState": "OFF"},
        ],
    )
    assert "1 refreshed, 1 deferred" in run("--date", target.day["date"], "--state", "active")
    assert Game.objects.get().game_finished is False
    assert not Gameday.objects.get().all_games_finished


def test_id_refresh_clears_stale_finished_day_without_claiming_missing_coverage(target):
    load(target)
    target.payload["gameState"] = "LIVE"
    target.register()
    run("--game-id", str(target.payload["id"]))
    day = Gameday.objects.get()
    assert day.all_games_uploaded is True
    assert day.all_games_finished is False
    assert Game.objects.get().game_finished is False
