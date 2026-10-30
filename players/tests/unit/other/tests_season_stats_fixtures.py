from copy import deepcopy
from types import SimpleNamespace

import pytest

from players import utils
from players.management.commands import upd_pls_tot


pytestmark = pytest.mark.unit

# Explicit table-to-SBS contract, independent of the production loader maps.
SKATER_FIELDS = {
    "games": "gamesPlayed",
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "plus_minus": "plusMinus",
    "penalty_min": "pim",
    "shots": "shots",
    "hits": "hits",
    "blocks": "blocked",
    "faceoff_wins": "faceoffsWon",
    "pp_points": "powerPlayPoints",
    "sh_points": "shorthandedPoints",
    "time_on_ice": "avgToi",
    "time_on_ice_pp": "powerPlayTimeOnIce",
    "time_on_ice_sh": "shortHandedTimeOnIce",
}
GOALIE_FIELDS = {
    "games": "gamesPlayed",
    "wins": "wins",
    "losses": "losses",
    "ot_losses": "otLosses",
    "goals_against_av": "goalsAgainstAvg",
    "saves_perc": "savePctg",
    "saves": "saves",
    "shotouts": "shutouts",
}
CORE_AVERAGE_FIELDS = {
    "goals_avg": "goals",
    "assists_avg": "assists",
    "points_avg": "points",
    "plus_minus_avg": "plusMinus",
    "penalty_min_avg": "pim",
    "shots_avg": "shots",
    "pp_points_avg": "powerPlayPoints",
    "sh_points_avg": "shorthandedPoints",
}


def test_sbs_field_contract_covers_every_table_statistic(season_stats_data):
    assert set(SKATER_FIELDS) == {"games", *utils.COLUMNS_TOT, *utils.COLUMNS_TOI}
    assert set(GOALIE_FIELDS) == {"games", *utils.COLUMNS_GOALIES}
    assert set(upd_pls_tot.CURRENT_SEASON_STATS_FIELD_MAP.items()) == {
        (sbs_key, field) for field, sbs_key in SKATER_FIELDS.items()
    }
    assert set(upd_pls_tot.GOALIE_CURRENT_SEASON_STATS_FIELD_MAP.items()) == {
        (sbs_key, field) for field, sbs_key in GOALIE_FIELDS.items()
    }
    expected = season_stats_data["cases"]["current_skater"]["expected"]
    assert set(expected["current_totals"]) == set(SKATER_FIELDS)
    assert set(expected["current_averages"]) == {"games", *utils.COLUMNS_AVG, *utils.COLUMNS_TOI}
    assert set(upd_pls_tot.CURRENT_SEASON_AVG_FIELD_MAP.values()) == set(
        expected["current_averages"]
    )


def test_old_season_rows_are_not_relabelled_as_current(season_stats_data):
    case = season_stats_data["cases"]["old_season_only"]

    rows = upd_pls_tot.get_season_by_season_stats(
        deepcopy(case["landing_season_totals"]), case["position_code"]
    )

    assert [(row["season"], row["goals"]) for row in rows] == [("2025-26", 20)]
    assert all(row["season"] != season_stats_data["requested_season"] for row in rows)


def test_current_skater_parses_regular_nhl_seasons_and_preserves_stats(season_stats_data):
    case = season_stats_data["cases"]["current_skater"]

    rows = upd_pls_tot.get_season_by_season_stats(
        deepcopy(case["landing_season_totals"]), case["position_code"]
    )

    assert [(row["season"], row["teamAbbr"]) for row in rows] == [
        ("2025-26", "BUF"),
        ("2026-27", "BUF"),
    ]
    current = rows[1]
    for field, expected in case["expected"]["current_totals"].items():
        assert current[SKATER_FIELDS[field]] == expected
    assert current["goals"] != case["snapshot"]["goals"]

    averages = upd_pls_tot.get_season_by_season_average_stats(deepcopy(rows))
    for field, sbs_key in CORE_AVERAGE_FIELDS.items():
        assert averages[1][sbs_key] == case["expected"]["current_averages"][field]
    assert current["goals"] == 2


def test_traded_skater_keeps_distinct_team_rows_and_per_team_denominators(season_stats_data):
    case = season_stats_data["cases"]["traded_skater"]

    rows = upd_pls_tot.get_season_by_season_stats(
        deepcopy(case["landing_season_totals"]), case["position_code"]
    )

    assert [(row["season"], row["teamAbbr"]) for row in rows] == [
        ("2026-27", "COL"),
        ("2026-27", "BUF"),
    ]
    for row in rows:
        for field, expected in case["expected"]["team_totals"][row["teamAbbr"]].items():
            assert row[SKATER_FIELDS[field]] == expected

    averages = upd_pls_tot.get_season_by_season_average_stats(deepcopy(rows))
    assert [row["goals"] for row in averages] == [0.25, 0.5]
    assert [row["gamesPlayed"] for row in averages] == [4, 6]


def test_goalie_season_parser_derives_saves_and_preserves_rate_stats(season_stats_data):
    case = season_stats_data["cases"]["current_goalie"]

    rows = upd_pls_tot.get_season_by_season_stats(
        deepcopy(case["landing_season_totals"]), case["position_code"]
    )

    assert len(rows) == 1
    assert rows[0]["season"] == season_stats_data["requested_season"]
    for field, expected in case["expected"]["current_totals"].items():
        assert rows[0][GOALIE_FIELDS[field]] == expected


def test_empty_enrichment_reports_preserve_unknown_fields_and_genuine_zero(
    season_stats_data, requests_mock
):
    case = season_stats_data["cases"]["missing_enrichment"]
    for report, response in case["stats_rest_responses"].items():
        requests_mock.get(upd_pls_tot.STATS_REST_SKATER_URL.format(report), json=response)
    # Preserve coverage of the legacy helper. The command's report-derived path
    # is covered separately by tests_season_loading.py.
    player = SimpleNamespace(nhl_id=9000001, stats_season_id="20252026")
    rows = upd_pls_tot.get_season_by_season_stats(
        deepcopy(case["landing_season_totals"]), case["position_code"]
    )

    enrichment = upd_pls_tot.get_skater_season_enrichment(player)
    totals = upd_pls_tot.enrich_season_stats_from_enrichment(rows, enrichment, "totals")
    averages = upd_pls_tot.get_season_by_season_average_stats(deepcopy(totals))

    assert requests_mock.call_count == 3
    assert enrichment == {}
    assert totals[0]["goals"] == 0
    assert totals[0]["blocked"] is None
    assert "hits" not in totals[0]
    assert "faceoffsWon" not in totals[0]
    assert "powerPlayTimeOnIce" not in totals[0]
    assert "shortHandedTimeOnIce" not in totals[0]
    assert averages[0]["goals"] == case["expected"]["current_averages"]["goals_avg"]
    assert averages[0]["assists"] == case["expected"]["current_averages"]["assists_avg"]
