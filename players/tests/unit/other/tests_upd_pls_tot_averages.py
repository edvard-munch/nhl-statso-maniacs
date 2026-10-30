from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from players.management.commands import upd_pls_tot


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "stats, expected",
    [
        ({"goals": 7, "gamesPlayed": 3}, 2.33),
        ({"goals": 0, "gamesPlayed": 3}, 0.0),
        ({"goals": -7, "gamesPlayed": 3}, -2.33),
        ({"gamesPlayed": 3}, None),
        ({"goals": None, "gamesPlayed": 3}, None),
        ({"goals": 7}, None),
        ({"goals": 7, "gamesPlayed": None}, None),
        ({"goals": 0, "gamesPlayed": 0}, None),
        ({}, None),
    ],
)
def test_get_average_handles_incomplete_stats(stats, expected):
    assert upd_pls_tot.get_average("goals", stats) == expected


def test_season_averages_handle_partial_and_zero_game_rows():
    seasons = [
        {"season": "2025-26", "gamesPlayed": 4, "goals": 2},
        {"season": "2026-27", "gamesPlayed": 0, "goals": 0},
    ]

    averages = upd_pls_tot.get_season_by_season_average_stats(seasons)

    assert averages[0]["goals"] == 0.5
    assert averages[0]["assists"] is None
    assert averages[1]["goals"] is None


@pytest.mark.parametrize("career_stats", [None, {}, {"gamesPlayed": 4, "goals": 2}])
def test_current_mode_saves_partial_career_data_and_can_run_again(monkeypatch, career_stats):
    player = SimpleNamespace(
        sbs_stats=[],
        sbs_stats_avg=[],
        career_stats=deepcopy(career_stats),
        career_stats_avg=None,
        save=Mock(),
    )
    enrichment = {
        upd_pls_tot.CAREER_ENRICHMENT_TOTALS: {"hits": 10},
        upd_pls_tot.CAREER_ENRICHMENT_AVERAGES: {"hits": 2.5},
    }
    monkeypatch.setattr(
        upd_pls_tot,
        "get_skater_career_enrichment",
        lambda player, session=None: deepcopy(enrichment),
    )

    upd_pls_tot.apply_current_mode_to_skater(player)

    assert player.career_stats == dict(career_stats or {}, hits=10)
    assert player.career_stats_avg["hits"] == 2.5
    assert player.career_stats_avg["goals"] == (0.5 if career_stats else None)
    assert player.career_stats_avg["assists"] is None
    player.save.assert_called_once_with(
        update_fields=[
            "career_stats",
            "career_stats_avg",
            "sbs_stats",
            "sbs_stats_avg",
            "multiteams_seasons",
        ]
    )
    first_updates = upd_pls_tot.get_current_mode_updates_for_skater(player)

    upd_pls_tot.apply_current_mode_to_skater(player)

    assert upd_pls_tot.get_current_mode_updates_for_skater(player) == first_updates
