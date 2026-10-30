from copy import deepcopy

import pytest

from players.management.commands import upd_pls_tot
from players.season_stats import GOALIE, SKATER, normalize_season_id, read_season_stats


pytestmark = pytest.mark.unit


@pytest.fixture
def stored_season_rows(season_stats_data):
    return {
        name: upd_pls_tot.get_season_by_season_stats(
            deepcopy(case["landing_season_totals"]), case["position_code"]
        )
        for name, case in season_stats_data["cases"].items()
    }


@pytest.mark.parametrize("season", [20262027, "20262027", "2026-27"])
@pytest.mark.parametrize(
    "case_name",
    ["old_season_only", "current_skater", "traded_skater", "current_goalie", "missing_enrichment"],
)
def test_reader_matches_season_contract(season_stats_data, stored_season_rows, case_name, season):
    case = season_stats_data["cases"][case_name]
    rows = stored_season_rows[case_name]
    before = deepcopy(rows)

    result = read_season_stats(
        rows, season, player_type=GOALIE if case["position_code"] == "G" else SKATER
    )

    if case["expected"]["current_totals"] is None:
        assert result is None
    else:
        assert result.season_id == "20262027"
        assert result.team_abbr is None
        for field, expected in case["expected"]["current_totals"].items():
            assert result.totals[field] == expected
        if case["position_code"] == "G":
            assert result.averages is None
        else:
            for field, expected in case["expected"]["current_averages"].items():
                assert result.averages[field] == expected
        if case_name == "current_skater":
            assert result.totals == case["expected"]["current_totals"]
            assert result.averages == case["expected"]["current_averages"]
    assert rows == before


@pytest.mark.parametrize("team", ["COL", "BUF"])
def test_reader_selects_team_contributions(season_stats_data, stored_season_rows, team):
    result = read_season_stats(
        stored_season_rows["traded_skater"], "2026-27", player_type=SKATER, team_abbr=team
    )

    assert result.team_abbr == team
    expected = season_stats_data["cases"]["traded_skater"]["expected"]["team_totals"][team]
    for field, value in expected.items():
        assert result.totals[field] == value
    assert result.averages["goals_avg"] == (0.25 if team == "COL" else 0.5)


def test_missing_team_does_not_fall_back_to_overall_stats(stored_season_rows):
    assert (
        read_season_stats(
            stored_season_rows["traded_skater"], "2026-27", player_type=SKATER, team_abbr="BOS"
        )
        is None
    )


def test_explicit_historical_selection_uses_that_season(stored_season_rows):
    result = read_season_stats(stored_season_rows["current_skater"], "2025-26", player_type=SKATER)

    assert result.season_id == "20252026"
    assert result.totals["games"] == 80
    assert result.totals["goals"] == 20
    assert result.averages["goals_avg"] == 0.25


def test_reader_rejects_other_competitions_and_ignores_unknown_seasons(stored_season_rows):
    rows = stored_season_rows["current_skater"]
    current = deepcopy(rows[1])
    rows.extend(
        [
            dict(current, gameTypeId=3, goals=100),
            dict(current, leagueAbbrev="AHL", goals=100),
            dict(current, season="unknown", goals=100),
            dict(current, season=20272028, goals=100),
        ]
    )

    result = read_season_stats(rows, "2026-27", player_type=SKATER)

    assert result.totals["goals"] == 2


@pytest.mark.parametrize("marker", ["TOT", "2TM", "10TM"])
def test_combined_row_prevents_double_counting_and_keeps_team_filter(stored_season_rows, marker):
    rows = stored_season_rows["traded_skater"]
    combined = dict(rows[0], teamAbbr=marker, gamesPlayed=10, goals=4, assists=5, points=9)
    rows.append(combined)

    overall = read_season_stats(rows, "2026-27", player_type=SKATER)
    colorado = read_season_stats(rows, "2026-27", player_type=SKATER, team_abbr="COL")

    assert overall.totals["games"] == 10
    assert overall.totals["goals"] == 4
    assert colorado.totals["games"] == 4
    assert colorado.totals["goals"] == 1


def test_missing_split_value_makes_overall_stat_unavailable(stored_season_rows):
    rows = stored_season_rows["traded_skater"]
    del rows[1]["hits"]
    rows[1]["shortHandedTimeOnIce"] = None

    result = read_season_stats(rows, "2026-27", player_type=SKATER)

    assert result.totals["hits"] is None
    assert result.averages["hits_avg"] is None
    assert result.totals["time_on_ice_sh"] is None
    assert result.totals["goals"] == 4
    assert result.totals["time_on_ice"] == "19:12"


@pytest.mark.parametrize("games", [0, None])
def test_no_denominator_leaves_averages_unavailable(games):
    result = read_season_stats(
        [{"season": "2026-27", "gamesPlayed": games, "goals": 0, "avgToi": "00:00"}],
        "2026-27",
        player_type=SKATER,
    )

    assert result.totals["games"] == games
    assert result.totals["goals"] == 0
    assert result.averages["goals_avg"] is None
    assert result.totals["time_on_ice"] is None


@pytest.mark.parametrize("time", [None, "", "invalid", "18:60"])
def test_invalid_time_is_unavailable(time):
    result = read_season_stats(
        [{"season": "2026-27", "gamesPlayed": 4, "avgToi": time}],
        "2026-27",
        player_type=SKATER,
    )

    assert result.totals["time_on_ice"] is None


def test_goalie_combination_uses_shots_for_save_percentage_and_keeps_gaa_unknown():
    rows = [
        {
            "season": "2026-27",
            "teamAbbr": "COL",
            "gamesPlayed": 2,
            "shotsAgainst": 50,
            "goalsAgainst": 5,
            "goalsAgainstAvg": 2.5,
            "savePctg": 0.9,
            "wins": 1,
            "losses": 1,
            "otLosses": 0,
            "shutouts": 0,
        },
        {
            "season": "2026-27",
            "teamAbbr": "BUF",
            "gamesPlayed": 4,
            "shotsAgainst": 150,
            "goalsAgainst": 12,
            "goalsAgainstAvg": 3.0,
            "savePctg": 0.92,
            "wins": 2,
            "losses": 1,
            "otLosses": 1,
            "shutouts": 1,
        },
    ]
    before = deepcopy(rows)

    result = read_season_stats(rows, "2026-27", player_type=GOALIE)

    assert result.totals == {
        "games": 6,
        "wins": 3,
        "losses": 2,
        "ot_losses": 1,
        "saves": 183,
        "shotouts": 1,
        "goals_against_av": None,
        "saves_perc": 0.915,
    }
    assert result.averages is None
    assert rows == before


def test_missing_goalie_shots_does_not_average_save_percentages():
    result = read_season_stats(
        [
            {"season": "2026-27", "teamAbbr": "COL", "savePctg": 0.9, "saves": 45},
            {"season": "2026-27", "teamAbbr": "BUF", "savePctg": 0.92, "saves": 138},
        ],
        "2026-27",
        player_type=GOALIE,
    )

    assert result.totals["saves"] == 183
    assert result.totals["saves_perc"] is None


def test_result_dictionaries_are_independent_of_source_and_each_other(stored_season_rows):
    rows = stored_season_rows["current_skater"]
    result = read_season_stats(rows, "2026-27", player_type=SKATER)
    result.totals["games"] = 999
    result.averages["goals_avg"] = 999

    assert result.averages["games"] == 10
    again = read_season_stats(rows, "2026-27", player_type=SKATER)
    assert again.totals["games"] == 10
    assert again.averages["goals_avg"] == 0.2


@pytest.mark.parametrize("rows", [None, [], {}])
def test_empty_stored_data_returns_no_statistics(rows):
    assert read_season_stats(rows, "2026-27", player_type=SKATER) is None


@pytest.mark.parametrize("season", [None, "", "2026", "2026-28", "20262028"])
def test_invalid_requested_seasons_fail_explicitly(season):
    with pytest.raises(ValueError, match="season"):
        read_season_stats([], season, player_type=SKATER)


def test_season_normalization_handles_century_boundary():
    assert normalize_season_id("2099-00") == "20992100"


@pytest.mark.parametrize("rows", [{"season": "2026-27"}, [None]])
def test_malformed_stored_data_fails_explicitly(rows):
    with pytest.raises(ValueError):
        read_season_stats(rows, "2026-27", player_type=SKATER)


@pytest.mark.parametrize("team", [None, "BUF"])
def test_duplicate_team_rows_fail_instead_of_double_counting(stored_season_rows, team):
    row = stored_season_rows["current_skater"][1]
    with pytest.raises(ValueError, match="distinct team"):
        read_season_stats([row, deepcopy(row)], "2026-27", player_type=SKATER, team_abbr=team)


def test_multiple_combined_rows_are_ambiguous(stored_season_rows):
    row = stored_season_rows["current_skater"][1]
    with pytest.raises(ValueError, match="ambiguous"):
        read_season_stats(
            [dict(row, teamAbbr="TOT"), dict(row, teamAbbr="2TM")],
            "2026-27",
            player_type=SKATER,
        )


def test_invalid_player_type_fails_explicitly():
    with pytest.raises(ValueError, match="player_type"):
        read_season_stats([], "2026-27", player_type="unknown")


@pytest.mark.parametrize("team", ["", "TOT", "2TM", 123])
def test_invalid_team_filter_fails_explicitly(team):
    with pytest.raises(ValueError, match="single team"):
        read_season_stats([], "2026-27", player_type=SKATER, team_abbr=team)


@pytest.mark.parametrize("value", [None, "", "2", True, float("nan"), float("inf")])
def test_non_numeric_or_unknown_counts_are_unavailable(value):
    result = read_season_stats(
        [{"season": "2026-27", "gamesPlayed": 4, "goals": value}],
        "2026-27",
        player_type=SKATER,
    )

    assert result.totals["goals"] is None
    assert result.averages["goals_avg"] is None


def test_zero_game_split_does_not_invalidate_available_time(stored_season_rows):
    rows = stored_season_rows["traded_skater"]
    rows.append({"season": "2026-27", "teamAbbr": "BOS", "gamesPlayed": 0})

    result = read_season_stats(rows, "2026-27", player_type=SKATER)

    assert result.totals["games"] == 10
    assert result.totals["time_on_ice"] == "19:12"
    # Counts remain unknown because the extra row does not supply them.
    assert result.totals["goals"] is None
