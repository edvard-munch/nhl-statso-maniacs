"""Read-only auditing uses real saved games and mocked NHL sources."""

from io import StringIO
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
import pytest

from players.management.commands import upd_gms
from players.models import Game, Gameday, Goalie, Skater
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game, load  # noqa: F401


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def audit_fixture(loaded_game, requests_mock):
    fixture = loaded_game
    fixture.payload["gameDate"] = fixture.day["date"]
    # Opponents share a sweater; reports must stay side-scoped.
    fixture.payload["playerByGameStats"]["homeTeam"]["forwards"][0]["sweaterNumber"] = 98
    for side in ("away", "home"):
        rosters = fixture.payload["playerByGameStats"][side + "Team"]
        rows = []
        for group in rosters.values():
            for player in group:
                rows.append(
                    "<tr><td>{}</td><td>{}</td><td>00:00</td></tr>".format(
                        player["sweaterNumber"], "01:15" if side == "away" else "02:30"
                    )
                )
        requests_mock.get(
            "https://reports.invalid/toi" + side.capitalize(),
            text="<table><tr><th>#</th><th>TOI PP</th><th>TOI SH</th></tr>"
            + "".join(rows)
            + "</table>",
        )
    fixture.game = load(fixture)
    return fixture


def audit(*args):
    output = StringIO()
    call_command("audit_game_toi", *args, "--json", stdout=output)
    return json.loads(output.getvalue())


def snapshot():
    return {
        model.__name__: list(model.objects.order_by("pk").values())
        for model in (Game, Gameday, Skater, Goalie)
    }


def test_matching_game_is_read_only_and_keeps_side_and_boxscore_precedence(audit_fixture):
    before = snapshot()
    with CaptureQueriesContext(connection) as queries:
        report = audit("--season", "20262027")
    assert snapshot() == before
    # PostgreSQL's iterator declares a read-only SELECT cursor.
    assert all(
        q["sql"].lstrip().upper().startswith("SELECT")
        or (q["sql"].lstrip().upper().startswith("DECLARE") and " FOR SELECT " in q["sql"].upper())
        for q in queries
    )
    assert report["summary"] == dict(
        games=1, match=12, mismatch=0, unverified=0, games_with_mismatches=0, games_unverified=0
    )
    records = report["records"]
    assert not any("bench" in r["player"] for r in records)
    assert (
        next(r for r in records if r["player_id"] == 900001 and r["field"] == "powerPlayToi")[
            "expected"
        ]
        == "01:15"
    )
    assert (
        next(r for r in records if r["player_id"] == 900005 and r["field"] == "powerPlayToi")[
            "expected"
        ]
        == "02:30"
    )
    assert (
        next(r for r in records if r["player_id"] == 900002 and r["field"] == "powerPlayToi")[
            "source"
        ]
        == "boxscore"
    )


def test_mismatches_identify_saved_values_without_repair(audit_fixture):
    player = audit_fixture.players["away_forward"]
    player.refresh_from_db()
    log = player.gamelog_stats[audit_fixture.day["date"]]
    log.update(powerPlayToi="00:00", shorthandedToi="04:15")
    player.save()
    before = snapshot()
    report = audit("--game-id", str(audit_fixture.game.nhl_id))
    assert report["summary"]["mismatch"] == 2
    assert report["summary"]["games_with_mismatches"] == 1
    mismatches = [r for r in report["records"] if r["status"] == "mismatch"]
    assert [(r["player_id"], r["stored"], r["expected"]) for r in mismatches] == [
        (900001, "00:00", "01:15"),
        (900001, "04:15", "00:00"),
    ]
    assert snapshot() == before


@pytest.mark.parametrize("failure", ["http", "empty", "html", "missing_link", "partial"])
def test_unavailable_report_values_are_unverified_never_zero(audit_fixture, requests_mock, failure):
    game_id = audit_fixture.game.nhl_id
    if failure == "missing_link":
        requests_mock.get(upd_gms.URL_RIGHT_RAIL.format(game_id), json={})
    else:
        body = {
            "empty": "",
            "html": "<html>Unavailable</html>",
            "partial": "<table><tr><th>#</th><th>TOI PP</th><th>TOI SH</th></tr>"
            "<tr><td>98</td><td>01:15</td><td>invalid</td></tr></table>",
        }.get(failure, "")
        requests_mock.get(
            "https://reports.invalid/toiAway",
            text=body,
            status_code=503 if failure == "http" else 200,
        )
    report = audit("--game-id", str(game_id))
    assert report["summary"]["unverified"] > 0
    assert report["summary"]["mismatch"] == 0
    assert report["summary"]["games_unverified"] == 1


@pytest.mark.parametrize("missing", ["player", "log", "field", "malformed"])
def test_missing_saved_data_is_not_reported_as_a_match(audit_fixture, missing):
    player = audit_fixture.players["away_forward"]
    player.refresh_from_db()
    if missing == "player":
        player.delete()
    else:
        if missing == "malformed":
            player.gamelog_stats = []
        elif missing == "log":
            del player.gamelog_stats[audit_fixture.day["date"]]
        else:
            del player.gamelog_stats[audit_fixture.day["date"]]["powerPlayToi"]
        player.save()
    report = audit("--season", "20262027")
    rows = [r for r in report["records"] if r.get("player_id") == player.nhl_id]
    assert any(r["status"] == ("mismatch" if missing == "field" else "unverified") for r in rows)


@pytest.mark.parametrize("failure", ["http", "json", "wrong_id", "wrong_date", "live", "roster"])
def test_bad_boxscore_is_unverified(audit_fixture, requests_mock, failure):
    payload = audit_fixture.payload
    if failure == "wrong_id":
        payload["id"] += 1
    if failure == "wrong_date":
        payload["gameDate"] = "2026-11-20"
    if failure == "live":
        payload["gameState"] = "LIVE"
    if failure == "roster":
        payload.pop("playerByGameStats")
    url = upd_gms.URL_BOXSCORE.format(audit_fixture.game.nhl_id)
    if failure in {"http", "json"}:
        requests_mock.get(url, text="unavailable", status_code=503 if failure == "http" else 200)
    else:
        requests_mock.get(url, json=payload)
    before = snapshot()
    report = audit("--season", "20262027")
    assert report["summary"]["games_unverified"] == 1
    assert report["summary"]["mismatch"] == 0
    assert snapshot() == before


def test_failed_game_does_not_stop_later_games(audit_fixture, requests_mock):
    Game.objects.create(nhl_id=2026020000, gameday=audit_fixture.game.gameday)
    requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020000), status_code=404)
    report = audit("--season", "20262027")
    assert report["summary"]["games"] == 2
    assert report["summary"]["games_unverified"] == 1
    assert report["summary"]["match"] == 12


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--season", "20262028"],
        ["--season", "2026-27"],
        ["--start-date", "bad", "--end-date", "2026-11-01"],
        ["--start-date", "2026-12-01", "--end-date", "2026-11-01"],
    ],
)
def test_invalid_selection_fails_before_requests(args, requests_mock):
    with pytest.raises(CommandError):
        audit(*args)
    assert requests_mock.call_count == 0


@pytest.mark.parametrize(
    "args",
    [
        ["--season", "20252026"],
        ["--start-date", "2026-11-22", "--end-date", "2026-11-30"],
        ["--game-id", "2026020999"],
    ],
)
def test_selection_excludes_other_games(audit_fixture, args, requests_mock):
    count = requests_mock.call_count
    assert audit(*args)["summary"]["games"] == 0
    assert requests_mock.call_count == count


def test_inclusive_dates_and_text_output(audit_fixture):
    output = StringIO()
    call_command(
        "audit_game_toi", "--start-date", "2026-11-21", "--end-date", "2026-11-21", stdout=output
    )
    assert "Read-only audit:" in output.getvalue()
    assert '"games": 1' in output.getvalue()


def test_overtime_shift_rows_do_not_hide_a_mismatch_or_reassign_totals(
    audit_fixture, requests_mock
):
    roster = audit_fixture.payload["playerByGameStats"]["awayTeam"]
    roster["forwards"][0]["sweaterNumber"] = 9
    roster["defense"][0]["sweaterNumber"] = 26
    roster["defense"][0].pop("powerPlayToi")
    audit_fixture.register()
    requests_mock.get(
        "https://reports.invalid/toiAway",
        text="""
        <table>
        <tr><td>9 EICHEL, JACK</td></tr>
        <tr><td>26</td><td>OT</td><td>0:00 / 5:00</td></tr>
        <tr><td>TOT</td><td>29</td><td>00:51</td><td>24:57</td>
            <td>20:14</td><td>02:14</td><td>02:29</td></tr>
        <tr><td>26 DOWD, NIC</td></tr>
        <tr><td>TOT</td><td>12</td><td>00:48</td><td>09:43</td>
            <td>08:15</td><td>00:00</td><td>01:28</td></tr>
        </table>
    """,
    )
    report = audit("--game-id", str(audit_fixture.game.nhl_id))
    rows = {(r.get("player_id"), r.get("field")): r for r in report["records"]}
    assert rows[900001, "powerPlayToi"]["expected"] == "02:14"
    assert rows[900001, "shorthandedToi"]["expected"] == "02:29"
    assert rows[900002, "powerPlayToi"]["expected"] == "00:00"
    assert rows[900002, "shorthandedToi"]["expected"] == "01:28"
    assert all(
        rows[pid, field]["status"] == "mismatch"
        for pid, field in [
            (900001, "powerPlayToi"),
            (900001, "shorthandedToi"),
            (900002, "powerPlayToi"),
            (900002, "shorthandedToi"),
        ]
    )
