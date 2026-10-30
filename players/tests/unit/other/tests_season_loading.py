from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from django.core.management.base import CommandError

from players import season_loading as loading
from players.management.commands import upd_pls, upd_pls_tot
from players.season_stats import read_season_stats


pytestmark = pytest.mark.unit


def register_case(requests_mock, case):
    for report, rows in case["reports"].items():

        def response(request, context, report=report):
            expression = request.qs["cayenneexp"][0]
            scoped = case["team_reports"]
            if "teamid=16" in expression:
                data = scoped["COL"][report]
            elif "teamid=7" in expression:
                data = scoped["BUF"][report]
            else:
                data = case["reports"][report]
            return {"data": deepcopy(data), "total": len(data)}

        requests_mock.get(loading.REPORT_URL.format(case["player_type"], report), json=response)


@pytest.mark.parametrize(
    "case_name",
    ["old_season_only", "current_skater", "traded_skater", "current_goalie", "missing_enrichment"],
)
def test_report_rows_match_shared_reader_contract(
    case_name, season_report_data, season_stats_data, requests_mock
):
    case = season_report_data[case_name]
    register_case(requests_mock, case)

    rows = loading.fetch_player_rows(
        case["player_id"], case["player_type"], {"COL": 16, "BUF": 7}, season="20262027"
    )
    result = read_season_stats(rows, "2026-27", player_type=case["player_type"])

    expected = season_stats_data["cases"][case_name]["expected"]
    if expected["current_totals"] is None:
        assert result is None
        return
    for field, value in expected["current_totals"].items():
        assert result.totals[field] == value
    for field, value in (expected.get("current_averages") or {}).items():
        assert result.averages[field] == value
    for team, values in expected.get("team_totals", {}).items():
        split = read_season_stats(rows, "2026-27", player_type=case["player_type"], team_abbr=team)
        for field, value in values.items():
            assert split.totals[field] == value
    if case_name == "traded_skater":
        assert [row["teamAbbr"] for row in rows] == ["TOT", "BUF", "COL"]
        assert requests_mock.call_count == 12


def test_pagination_fetches_all_rows_including_final_partial_page(requests_mock):
    first = [{"playerId": index, "seasonId": 20262027} for index in range(100)]
    last = [{"playerId": 100, "seasonId": 20262027}]
    requests_mock.get(
        loading.REPORT_URL.format("skater", "summary"),
        [
            {"json": {"data": first, "total": 101}},
            {"json": {"data": last, "total": 101}},
        ],
    )

    rows = loading.fetch_report("summary", "skater", season="20262027")

    assert rows == first + last
    assert [request.qs["start"] for request in requests_mock.request_history] == [["0"], ["100"]]
    assert all(
        request.timeout == loading.REPORT_TIMEOUT for request in requests_mock.request_history
    )


@pytest.mark.parametrize(
    "failure",
    [
        {"status_code": 503},
        {"text": "<html>upstream failure</html>"},
        {"exc": requests.ConnectionError("offline")},
        {"json": {"data": []}},
    ],
)
def test_failed_report_raises_instead_of_becoming_empty_data(requests_mock, failure):
    requests_mock.get(loading.REPORT_URL.format("skater", "summary"), **failure)

    with pytest.raises(CommandError, match="summary"):
        loading.fetch_report("summary", "skater", season="20262027")

    assert requests_mock.call_count == loading.REPORT_ATTEMPTS


def test_temporary_http_error_retries_successfully(requests_mock):
    requests_mock.get(
        loading.REPORT_URL.format("skater", "summary"),
        [
            {"status_code": 503},
            {"json": {"data": [], "total": 0}},
        ],
    )

    assert loading.fetch_report("summary", "skater") == []
    assert requests_mock.call_count == 2


def test_truncated_pagination_is_rejected(requests_mock):
    requests_mock.get(loading.REPORT_URL.format("skater", "summary"), json={"data": [], "total": 1})
    with pytest.raises(CommandError, match="pagination"):
        loading.fetch_report("summary", "skater")


def test_wrong_season_is_rejected(requests_mock):
    requests_mock.get(
        loading.REPORT_URL.format("skater", "summary"),
        json={
            "data": [{"playerId": 1, "seasonId": 20252026}],
            "total": 1,
        },
    )
    with pytest.raises(CommandError, match="different season"):
        loading.fetch_report("summary", "skater", season="20262027")


def test_historical_team_registry_resolves_missing_team_ids(season_report_data, requests_mock):
    case = season_report_data["traded_skater"]
    register_case(requests_mock, case)
    requests_mock.get(
        "https://api.nhle.com/stats/rest/en/team",
        json={
            "data": [{"id": 16, "triCode": "COL", "rawTricode": "COL"}],
            "total": 1,
        },
    )
    teams = {"BUF": 7}

    rows = loading.fetch_player_rows(case["player_id"], "skater", teams, season="20262027")

    assert teams == {"BUF": 7, "COL": 16}
    assert {row["teamAbbr"] for row in rows} == {"TOT", "COL", "BUF"}


def test_split_that_is_not_team_scoped_is_rejected(season_report_data, requests_mock):
    case = season_report_data["traded_skater"]
    case["team_reports"]["BUF"]["summary"][0]["teamAbbrevs"] = "BUF,COL"
    register_case(requests_mock, case)
    with pytest.raises(CommandError, match="unscoped"):
        loading.fetch_player_rows(
            case["player_id"], "skater", {"BUF": 7, "COL": 16}, season="20262027"
        )


def test_disagreeing_reports_are_rejected(season_report_data):
    case = season_report_data["current_skater"]
    case["reports"]["realtime"][0]["gamesPlayed"] = 80
    with pytest.raises(CommandError, match="disagree"):
        loading.assemble_player_rows(case["reports"], "skater", case["player_id"], {})


def test_new_rows_replace_only_refreshed_season_and_reset_snapshot(season_report_data):
    case = season_report_data["missing_enrichment"]
    fresh = loading.assemble_player_rows(case["reports"], "skater", case["player_id"], {})
    history = {
        "season": "2025-26",
        "teamAbbr": "BUF",
        "gamesPlayed": 80,
        "goals": 20,
        "custom": "keep",
    }
    contaminated = dict(history, season="2026-27", hits=60, faceoffsWon=100)
    player = SimpleNamespace(
        sbs_stats=[history, contaminated], sbs_stats_avg=[dict(history)], stats_season_id="20252026"
    )
    before = deepcopy(player)

    updates = loading.season_row_updates(player, fresh, "skater")

    assert player.__dict__ == before.__dict__
    assert updates["sbs_stats"][0] == history
    assert updates["sbs_stats_avg"][0] == history
    assert updates["sbs_stats"][1]["hits"] is None
    assert updates["goals"] == 0
    assert updates["goals_avg"] == 0.0
    assert updates["hits"] is None
    assert updates["time_on_ice_pp"] == ""
    assert updates["stats_season_id"] == "20262027"
    for field, value in updates.items():
        setattr(player, field, value)
    assert loading.season_row_updates(player, fresh, "skater") == updates


def test_empty_summary_preserves_existing_rows_and_season_marker():
    player = SimpleNamespace(
        sbs_stats=[{"season": "2025-26", "gamesPlayed": 80}], stats_season_id="20252026"
    )
    assert loading.season_row_updates(player, [], "skater") == {}
    assert player.stats_season_id == "20252026"


def test_historical_refresh_cannot_replace_newer_snapshot(season_report_data):
    case = season_report_data["current_skater"]
    fresh = loading.assemble_player_rows(case["reports"], "skater", case["player_id"], {})
    player = SimpleNamespace(sbs_stats=[], sbs_stats_avg=[], stats_season_id="20272028")
    updates = loading.season_row_updates(player, fresh, "skater")
    assert updates["sbs_stats"][0]["goals"] == 2
    assert "stats_season_id" not in updates
    assert "goals" not in updates


def test_current_mode_failure_does_not_save_or_mutate_player(monkeypatch):
    player = SimpleNamespace(nhl_id=1, sbs_stats=[{"season": "2025-26"}], save=Mock())
    before = deepcopy(player.sbs_stats)
    monkeypatch.setattr(
        upd_pls_tot, "get_report_season_rows", Mock(side_effect=CommandError("offline"))
    )

    with pytest.raises(CommandError, match="offline"):
        upd_pls_tot.apply_current_mode_to_skater(player, season="20262027")

    assert player.sbs_stats == before
    player.save.assert_not_called()


def test_upd_pls_report_failure_occurs_before_any_import(monkeypatch):
    monkeypatch.setattr(upd_pls, "get_season_id", lambda: "20262027")
    monkeypatch.setattr(upd_pls.Team.objects, "values_list", lambda *args: [])
    monkeypatch.setattr(loading, "fetch_report", Mock(side_effect=CommandError("offline")))
    importer = Mock()
    monkeypatch.setattr(upd_pls, "import_player", importer)

    with pytest.raises(CommandError, match="offline"):
        upd_pls.Command().handle()

    importer.assert_not_called()
