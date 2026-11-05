"""Read-only auditing uses real saved games and mocked NHL sources."""

from io import StringIO
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
import pytest

from players.management.commands import audit_game_toi, upd_gms
from players.models import Game, Gameday, Goalie, Skater
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game, load  # noqa: F401


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def no_audit_wait(monkeypatch):
    monkeypatch.setattr(audit_game_toi, "sleep", lambda seconds: None)


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
    Game.objects.create(nhl_id=2026020000, gameday=audit_fixture.game.gameday, game_finished=True)
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


@pytest.mark.parametrize("include", [False, True])
def test_locally_unfinished_games_require_explicit_opt_in(audit_fixture, requests_mock, include):
    Game.objects.filter(pk=audit_fixture.game.pk).update(game_finished=False)
    count = requests_mock.call_count
    args = ["--season", "20262027"] + (["--include-unfinished"] if include else [])
    report = audit(*args)
    assert report["summary"]["games"] == (1 if include else 0)
    if not include:
        assert requests_mock.call_count == count


def test_progress_stays_on_stderr_when_stdout_is_json(audit_fixture):
    output, progress = StringIO(), StringIO()
    call_command("audit_game_toi", "--season", "20262027", "--json", stdout=output, stderr=progress)
    assert json.loads(output.getvalue())["summary"]["games"] == 1
    terminal = progress.getvalue()
    assert "[1/1] 2026-11-21" in terminal
    assert str(audit_fixture.game.nhl_id) in terminal
    assert "games with mismatches" in terminal
    assert "unverified" in terminal
    assert "elapsed" in terminal
    assert "finished" in terminal


@pytest.mark.parametrize("header,expected_wait", [("12", 12), ("invalid", 5), (None, 5)])
def test_rate_limit_retries_apply_to_report_requests(
    audit_fixture, requests_mock, monkeypatch, header, expected_wait
):
    waits = []
    monkeypatch.setattr(audit_game_toi, "sleep", waits.append)
    url = "https://reports.invalid/toiAway"
    original = requests_mock.get(
        url,
        [
            {"status_code": 429, "headers": {"Retry-After": header} if header else {}},
            {
                "text": "<table><tr><th>#</th><th>TOI PP</th><th>TOI SH</th></tr>"
                "<tr><td>98</td><td>01:15</td><td>00:00</td></tr></table>"
            },
        ],
    )
    output, progress = StringIO(), StringIO()
    call_command("audit_game_toi", "--season", "20262027", "--json", stdout=output, stderr=progress)
    assert original.call_count == 2
    assert expected_wait in waits
    assert "Rate limited: waiting" in progress.getvalue()
    assert "stopping" not in progress.getvalue()
    assert json.loads(output.getvalue())["summary"]["mismatch"] == 0


def test_request_pacing_covers_all_endpoints(requests_mock, monkeypatch):
    now = [0.0]
    waits = []

    def advance(seconds):
        waits.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(audit_game_toi, "sleep", advance)
    monkeypatch.setattr(audit_game_toi, "monotonic", lambda: now[0])
    requests_mock.get("https://source.invalid/json", json={})
    requests_mock.get("https://reports.invalid/html", text="report")
    with audit_game_toi.AuditSession(2, lambda message: None) as session:
        session.get("https://source.invalid/json")
        session.get("https://reports.invalid/html")
        session.get("https://source.invalid/json")
    assert waits == [2, 2]


@pytest.mark.parametrize("retry_after", [None, "120"])
def test_persistent_rate_limit_stops_and_checkpoints_before_next_game(
    audit_fixture, requests_mock, tmp_path, retry_after
):
    Game.objects.create(nhl_id=2026020002, game_finished=True, gameday=audit_fixture.game.gameday)
    mock = requests_mock.get(
        upd_gms.URL_BOXSCORE.format(audit_fixture.game.nhl_id),
        status_code=429,
        headers={"Retry-After": retry_after} if retry_after else {},
    )
    output, progress = StringIO(), StringIO()
    path = tmp_path / "audit.jsonl"
    with pytest.raises(CommandError, match="stopping"):
        call_command(
            "audit_game_toi",
            "--season",
            "20262027",
            "--json",
            "--output",
            str(path),
            stdout=output,
            stderr=progress,
        )
    assert mock.call_count == (1 if retry_after else 3)
    report = json.loads(output.getvalue())
    assert report["summary"]["games"] == 1
    assert report["summary"]["games_unverified"] == 1
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[-1]["records"][0]["status"] == "unverified"
    assert str(path) in progress.getvalue()
    assert "Audit stopped" in progress.getvalue()


def test_resume_skips_verified_games_without_http(audit_fixture, requests_mock, tmp_path):
    path = tmp_path / "audit.jsonl"
    first = audit("--season", "20262027", "--output", str(path))
    count = requests_mock.call_count
    resumed = audit("--season", "20262027", "--output", str(path), "--resume")
    assert resumed == first
    assert requests_mock.call_count == count
    assert len(path.read_text().splitlines()) == 2


def test_resume_retries_unverified_and_replaces_previous_result(
    audit_fixture, requests_mock, tmp_path
):
    path = tmp_path / "audit.jsonl"
    url = upd_gms.URL_BOXSCORE.format(audit_fixture.game.nhl_id)
    requests_mock.get(url, status_code=404)
    first = audit("--season", "20262027", "--output", str(path))
    assert first["summary"]["games_unverified"] == 1
    audit_fixture.register()
    resumed = audit("--season", "20262027", "--output", str(path), "--resume")
    assert resumed["summary"]["games_unverified"] == 0
    assert resumed["summary"]["games"] == 1
    assert resumed["summary"]["match"] == 12
    assert len(path.read_text().splitlines()) == 3
    count = requests_mock.call_count
    assert audit("--season", "20262027", "--output", str(path), "--resume") == resumed
    assert requests_mock.call_count == count


def test_interruption_preserves_first_game_and_resume_completes_remaining(
    audit_fixture, requests_mock, monkeypatch, tmp_path
):
    second = Game.objects.create(
        nhl_id=2026020002, game_finished=True, gameday=audit_fixture.game.gameday
    )
    original = audit_game_toi.audit_game
    path = tmp_path / "audit.jsonl"

    def interrupt(game, session):
        if game.nhl_id == second.nhl_id:
            # The previous game is flushed before the next game starts.
            assert len(path.read_text().splitlines()) == 2
            raise KeyboardInterrupt
        return original(game, session)

    monkeypatch.setattr(audit_game_toi, "audit_game", interrupt)
    output = StringIO()
    with pytest.raises(CommandError, match="Interrupted"):
        call_command(
            "audit_game_toi",
            "--season",
            "20262027",
            "--output",
            str(path),
            "--json",
            stdout=output,
            stderr=StringIO(),
        )
    assert json.loads(output.getvalue())["summary"]["games"] == 1
    monkeypatch.setattr(audit_game_toi, "audit_game", original)
    requests_mock.get(upd_gms.URL_BOXSCORE.format(second.nhl_id), status_code=404)
    count = requests_mock.call_count
    resumed = audit("--season", "20262027", "--output", str(path), "--resume")
    assert requests_mock.call_count == count + 1
    assert resumed["summary"]["games"] == 2


def test_resume_recovers_partial_last_write(audit_fixture, tmp_path):
    path = tmp_path / "audit.jsonl"
    first = audit("--season", "20262027", "--output", str(path))
    complete = path.read_bytes()
    with path.open("ab") as file:
        file.write(b'{"type": "game", "game_id":')
    assert audit("--season", "20262027", "--output", str(path), "--resume") == first
    assert path.read_bytes() == complete


def test_checkpoint_refuses_overwrite_and_wrong_selection(audit_fixture, tmp_path):
    path = tmp_path / "audit.jsonl"
    audit("--season", "20262027", "--output", str(path))
    before = path.read_bytes()
    with pytest.raises(CommandError, match="checkpoint"):
        audit("--season", "20262027", "--output", str(path))
    with pytest.raises(CommandError, match="selection"):
        audit("--season", "20252026", "--output", str(path), "--resume")
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        ["--resume"],
        ["--request-delay", "-1"],
        ["--request-delay", "nan"],
        ["--request-delay", "inf"],
    ],
)
def test_invalid_hardening_options_fail_before_requests(requests_mock, args):
    with pytest.raises(CommandError):
        audit("--season", "20262027", *args)
    assert requests_mock.call_count == 0


def test_http_date_retry_after_is_respected(requests_mock, monkeypatch):
    from datetime import datetime, timezone

    fixed = datetime(2026, 11, 5, 8, 0, 0, tzinfo=timezone.utc)

    class Clock:
        @staticmethod
        def now(tz):
            return fixed

    monkeypatch.setattr(audit_game_toi, "datetime", Clock)
    waits = []
    monkeypatch.setattr(audit_game_toi, "sleep", waits.append)
    requests_mock.get(
        "https://source.invalid/rate",
        [
            {"status_code": 429, "headers": {"Retry-After": "Thu, 05 Nov 2026 08:00:30 GMT"}},
            {"json": {}},
        ],
    )
    with audit_game_toi.AuditSession(0, lambda message: None) as session:
        assert session.get("https://source.invalid/rate").status_code == 200
    assert 30 in waits


def test_exponential_backoff_is_bounded_without_nested_json_retries(requests_mock, monkeypatch):
    waits = []
    monkeypatch.setattr(audit_game_toi, "sleep", waits.append)
    mock = requests_mock.get(upd_gms.URL_BOXSCORE.format(2026020001), status_code=429)
    with audit_game_toi.AuditSession(0, lambda message: None) as session:
        with pytest.raises(audit_game_toi.AuditRateLimitError):
            upd_gms.get_game_data(2026020001, upd_gms.URL_BOXSCORE, session)
    assert mock.call_count == 3
    assert [w for w in waits if w >= 5] == [5, 10]


def test_corrupt_checkpoint_is_rejected_without_modification(audit_fixture, tmp_path):
    path = tmp_path / "audit.jsonl"
    audit("--season", "20262027", "--output", str(path))
    with path.open("ab") as file:
        file.write(b'{"type": "game", "game_id": 2026020001, "records": []}\n')
    before = path.read_bytes()
    with pytest.raises(CommandError, match="Invalid game checkpoint"):
        audit("--season", "20262027", "--output", str(path), "--resume")
    assert path.read_bytes() == before
