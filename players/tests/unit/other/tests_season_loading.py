from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import json
from pathlib import Path

import pytest
import requests
from django.core.management.base import CommandError

from players import season_loading as loading
from players.management.commands import upd_pls, upd_pls_tot
from players.season_stats import read_season_stats


pytestmark = pytest.mark.unit


@pytest.fixture
def mermis_reports(requests_mock):
    # Public NHL stats/rest reports for Mermis, 2024-25, with and without teamId.
    path = Path(__file__).parents[2] / "fixtures/mermis_20242025_reports.json"
    reports = json.loads(path.read_text())
    registry = [
        {"id": 10, "triCode": "TOR", "rawTricode": "TOR"},
        {"id": 59, "triCode": "UTA", "rawTricode": "UTA"},
        {"id": 68, "triCode": "UTA", "rawTricode": "UTA"},
    ]
    requests_mock.get(
        "https://api.nhle.com/stats/rest/en/team", json={"data": registry, "total": len(registry)}
    )
    for report in loading.REPORTS["skater"]:

        def response(request, context, report=report):
            expression = request.qs["cayenneexp"][0]
            team = next((key for key in reports if "teamid=" + key in expression), "all")
            rows = reports[team][report]
            return {"data": rows, "total": len(rows)}

        requests_mock.get(loading.REPORT_URL.format("skater", report), json=response)
    return reports, registry


@pytest.mark.parametrize("teams", [{"TOR": 10, "UTA": 68}, {"TOR": 10}])
def test_historical_utah_split_uses_the_id_that_played_in_that_season(mermis_reports, teams):
    rows = loading.fetch_player_rows(8477541, "skater", teams, season="20242025")
    assert [(row["teamAbbr"], row["gamesPlayed"], row["shots"]) for row in rows] == [
        ("TOT", 4, 6),
        ("TOR", 3, 4),
        ("UTA", 1, 2),
    ]
    assert rows[-1]["avgToi"] == "10:47"
    assert teams["UTA"] == (59, 68)


def test_registry_keeps_duplicate_team_abbreviations_in_either_order(mermis_reports, requests_mock):
    assert loading.fetch_team_ids()["UTA"] == (59, 68)
    mermis_reports[1].reverse()
    requests_mock.get(
        loading.TEAM_REGISTRY_URL,
        json={"data": mermis_reports[1], "total": len(mermis_reports[1])},
    )
    assert loading.fetch_team_ids()["UTA"] == (59, 68)


def test_team_id_resolution_is_not_cached_across_seasons(mermis_reports):
    reports, _ = mermis_reports
    teams = {"TOR": 10, "UTA": 68}
    loading.fetch_player_rows(8477541, "skater", teams, season="20242025")
    # Simulate another season in which the new Utah ID has the contribution.
    for scoped in reports.values():
        for rows in scoped.values():
            for row in rows:
                row["seasonId"] = 20252026
    reports["59"], reports["68"] = reports["68"], reports["59"]
    rows = loading.fetch_player_rows(8477541, "skater", teams, season="20252026")
    assert [(row["teamAbbr"], row["gamesPlayed"]) for row in rows] == [
        ("TOT", 4),
        ("TOR", 3),
        ("UTA", 1),
    ]


def test_multiple_team_ids_with_season_rows_are_rejected(mermis_reports):
    reports, _ = mermis_reports
    reports["68"] = deepcopy(reports["59"])
    with pytest.raises(CommandError, match="Ambiguous UTA team IDs"):
        loading.fetch_player_rows(8477541, "skater", {"TOR": 10}, season="20242025")


def test_missing_historical_split_still_fails(mermis_reports):
    reports, _ = mermis_reports
    reports["59"] = deepcopy(reports["68"])
    with pytest.raises(CommandError, match="Missing or invalid UTA split"):
        loading.fetch_player_rows(8477541, "skater", {"TOR": 10, "UTA": 68}, season="20242025")


def test_historical_candidate_request_failure_is_not_treated_as_missing(
    mermis_reports, requests_mock
):
    requests_mock.get(
        loading.REPORT_URL.format("skater", "summary"),
        additional_matcher=lambda request: "teamid=59" in request.qs["cayenneexp"][0],
        status_code=503,
    )
    with pytest.raises(CommandError, match="Failed skater summary"):
        loading.fetch_player_rows(8477541, "skater", {"TOR": 10, "UTA": 68}, season="20242025")


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


@pytest.mark.parametrize("labels", ["BUF,COL", "COL, BUF"])
def test_scoped_counts_with_season_wide_team_labels_are_accepted(
    season_report_data, requests_mock, labels
):
    case = season_report_data["traded_skater"]
    for reports in case["team_reports"].values():
        for rows in reports.values():
            for row in rows:
                row["teamAbbrevs"] = labels
    register_case(requests_mock, case)
    rows = loading.fetch_player_rows(
        case["player_id"], "skater", {"BUF": 7, "COL": 16}, season="20262027"
    )
    assert [(row["teamAbbr"], row["gamesPlayed"], row["goals"]) for row in rows] == [
        ("TOT", 10, 4),
        ("BUF", 6, 3),
        ("COL", 4, 1),
    ]
    assert all(
        "teamid=" in request.qs["cayenneexp"][0] for request in requests_mock.request_history[4:]
    )


@pytest.mark.parametrize("labels", ["COL", "BUF,NJD", "", None])
def test_split_with_missing_or_unrelated_team_identity_is_rejected(
    season_report_data, requests_mock, labels
):
    case = season_report_data["traded_skater"]
    case["team_reports"]["BUF"]["summary"][0]["teamAbbrevs"] = labels
    register_case(requests_mock, case)
    with pytest.raises(CommandError, match="Missing or invalid BUF split"):
        loading.fetch_player_rows(
            case["player_id"], "skater", {"BUF": 7, "COL": 16}, season="20262027"
        )


def test_ignored_team_filter_is_rejected_by_count_reconciliation(season_report_data, requests_mock):
    case = season_report_data["traded_skater"]
    for team in case["team_reports"]:
        case["team_reports"][team] = deepcopy(case["reports"])
    register_case(requests_mock, case)
    with pytest.raises(CommandError, match="Team splits disagree with combined gamesPlayed"):
        loading.fetch_player_rows(
            case["player_id"], "skater", {"BUF": 7, "COL": 16}, season="20262027"
        )


def test_goalie_team_labels_can_stay_combined_while_rates_are_scoped(requests_mock):
    combined = dict(
        playerId=8482076,
        seasonId=20262027,
        teamAbbrevs="NJD,WPG",
        gamesPlayed=6,
        wins=2,
        losses=3,
        otLosses=0,
        saves=117,
        shotsAgainst=132,
        goalsAgainst=15,
        shutouts=0,
        goalsAgainstAverage=2.85956,
        savePct=0.88636,
    )
    njd = dict(
        combined,
        gamesPlayed=4,
        wins=2,
        losses=2,
        saves=75,
        shotsAgainst=86,
        goalsAgainst=11,
        goalsAgainstAverage=2.77699,
        savePct=0.87209,
    )
    wpg = dict(
        combined,
        gamesPlayed=2,
        wins=0,
        losses=1,
        saves=42,
        shotsAgainst=46,
        goalsAgainst=4,
        goalsAgainstAverage=3.11418,
        savePct=0.91304,
    )

    def response(request, context):
        expression = request.qs["cayenneexp"][0]
        row = njd if "teamid=1" in expression else wpg if "teamid=52" in expression else combined
        return {"data": [row], "total": 1}

    requests_mock.get(loading.REPORT_URL.format("goalie", "summary"), json=response)
    rows = loading.fetch_player_rows(8482076, "goalie", {"NJD": 1, "WPG": 52}, season="20262027")
    assert [(row["teamAbbr"], row["gamesPlayed"], row["saves"]) for row in rows] == [
        ("TOT", 6, 117),
        ("NJD", 4, 75),
        ("WPG", 2, 42),
    ]
    assert rows[1]["savePctg"] == 0.87209
    assert rows[2]["goalsAgainstAvg"] == 3.11418


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
