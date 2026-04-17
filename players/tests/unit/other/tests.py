from datetime import datetime
from types import SimpleNamespace

import pytest

# from correct.package import __BASE_URL
from django.core.management import call_command
from players.management.commands import upd_pls, upd_pls_tot


# @pytest.fixture(scope='session')
# def django_db_setup(django_db_setup, django_db_blocker):
#     with django_db_blocker.unblock():
#         call_command('loaddata', 'team_objects.json')
#         call_command('loaddata', 'skater_objects.json')
#         call_command('loaddata', 'goalie_objects.json')
#         call_command('loaddata', 'gameday_objects.json')
#         call_command('loaddata', 'games_objects.json')


@pytest.mark.parametrize(
    "born, today, age",
    [
        ["1984-06-04", "2020-06-04", 36],
        ["1984-06-04", "2007-06-04", 23],
        ["1984-06-05", "2020-06-04", 35],
        ["1973-06-08", "2020-06-04", 46],
        ["1993-04-17", "2020-06-04", 27],
        ["1993-04-17", "2020-04-16", 26],
    ],
)
def test_calculate_age(born, today, age):
    born = datetime.strptime(born, "%Y-%m-%d")
    today = datetime.strptime(today, "%Y-%m-%d")

    assert upd_pls.calculate_age(born, today) == age


@pytest.mark.parametrize(
    "dict_, key, expected",
    [
        [{"name": "John"}, "name", "John"],
        [{"name": "John"}, "weight", ""],
        [{"name": "John", "weight": ""}, "weight", ""],
    ],
)
def test_get_char_field_value(dict_, key, expected):
    assert upd_pls.get_char_field_value(dict_, key) == expected


def test_enrich_current_season_stats_from_player_updates_missing_current_season_fields_only():
    seasons_stats = [
        {
            "season": "2024-25",
            "hits": None,
            "blocked": None,
            "faceoffsWon": None,
            "powerPlayTimeOnIce": "",
            "shortHandedTimeOnIce": "",
        },
        {
            "season": "2025-26",
            "hits": None,
            "blocked": None,
            "faceoffsWon": None,
            "powerPlayTimeOnIce": "",
            "shortHandedTimeOnIce": "",
        },
    ]
    player = SimpleNamespace(
        stats_season_id="20252026",
        hits=10,
        blocks=5,
        faceoff_wins=20,
        time_on_ice_pp="02:34",
        time_on_ice_sh="00:45",
    )

    enriched = upd_pls_tot.enrich_current_season_stats_from_player(
        seasons_stats, player, upd_pls_tot.CURRENT_SEASON_STATS_FIELD_MAP
    )

    assert enriched[0] == {
        "season": "2024-25",
        "hits": None,
        "blocked": None,
        "faceoffsWon": None,
        "powerPlayTimeOnIce": "",
        "shortHandedTimeOnIce": "",
    }
    assert enriched[1] == {
        "season": "2025-26",
        "hits": 10,
        "blocked": 5,
        "faceoffsWon": 20,
        "powerPlayTimeOnIce": "02:34",
        "shortHandedTimeOnIce": "00:45",
    }


def test_enrich_current_season_stats_from_player_skips_without_stats_season_id():
    seasons_stats = [{"season": "2025-26", "hits": None}]
    player = SimpleNamespace(stats_season_id=None, hits=10)

    enriched = upd_pls_tot.enrich_current_season_stats_from_player(
        seasons_stats, player, upd_pls_tot.CURRENT_SEASON_STATS_FIELD_MAP
    )

    assert enriched == [{"season": "2025-26", "hits": None}]


def test_enrich_current_season_stats_from_player_can_overwrite_existing_values():
    seasons_stats = [{"season": "2025-26", "hits": 37}]
    player = SimpleNamespace(stats_season_id="20252026", hits_avg=0.46)

    enriched = upd_pls_tot.enrich_current_season_stats_from_player(
        seasons_stats,
        player,
        {"hits": "hits_avg"},
        overwrite_existing=True,
    )

    assert enriched == [{"season": "2025-26", "hits": 0.46}]


def test_enrich_season_stats_from_enrichment_updates_non_current_seasons():
    seasons_stats = [
        {"season": "2023-24", "hits": None, "blocked": None, "faceoffsWon": None},
        {"season": "2025-26", "hits": 37, "blocked": 65, "faceoffsWon": 723},
    ]
    season_enrichment = {
        "2023-24": {
            "totals": {"hits": 200, "blocked": 31, "faceoffsWon": 700},
            "averages": {"hits": 2.44, "blocked": 0.38, "faceoffsWon": 8.54},
        }
    }

    enriched = upd_pls_tot.enrich_season_stats_from_enrichment(
        seasons_stats, season_enrichment, "totals"
    )

    assert enriched == [
        {"season": "2023-24", "hits": 200, "blocked": 31, "faceoffsWon": 700},
        {"season": "2025-26", "hits": 37, "blocked": 65, "faceoffsWon": 723},
    ]


def test_enrich_season_stats_from_enrichment_overwrites_for_avg_bucket_when_enabled():
    seasons_stats_avg = [
        {"season": "2023-24", "hits": 200, "blocked": 31, "faceoffsWon": 700},
    ]
    season_enrichment = {
        "2023-24": {
            "averages": {"hits": 2.44, "blocked": 0.38, "faceoffsWon": 8.54},
        }
    }

    enriched = upd_pls_tot.enrich_season_stats_from_enrichment(
        seasons_stats_avg,
        season_enrichment,
        "averages",
        overwrite_existing=True,
    )

    assert enriched == [
        {"season": "2023-24", "hits": 2.44, "blocked": 0.38, "faceoffsWon": 8.54},
    ]


def test_enrich_career_stats_fills_only_missing_without_overwrite():
    career_stats = {
        "hits": None,
        "blocked": None,
        "powerPlayPoints": 111,
        "shorthandedPoints": None,
        "powerPlayTimeOnIcePerGame": None,
        "shortHandedTimeOnIcePerGame": None,
    }
    career_enrichment = {
        upd_pls_tot.CAREER_ENRICHMENT_TOTALS: {
            "hits": 534,
            "blocked": 461,
            "powerPlayPoints": 238,
            "shorthandedPoints": 20,
            "powerPlayTimeOnIcePerGame": "03:15",
            "shortHandedTimeOnIcePerGame": "01:51",
        }
    }

    enriched = upd_pls_tot.enrich_career_stats(
        career_stats,
        career_enrichment,
        upd_pls_tot.CAREER_ENRICHMENT_TOTALS,
    )

    assert enriched == {
        "hits": 534,
        "blocked": 461,
        "powerPlayPoints": 111,
        "shorthandedPoints": 20,
        "powerPlayTimeOnIcePerGame": "03:15",
        "shortHandedTimeOnIcePerGame": "01:51",
    }


def test_enrich_career_stats_overwrites_when_enabled():
    career_stats_avg = {"avgToi": "17:12"}
    career_enrichment = {
        upd_pls_tot.CAREER_ENRICHMENT_AVERAGES: {
            "avgToi": "18:00",
            "powerPlayTimeOnIcePerGame": "03:15",
            "shortHandedTimeOnIcePerGame": "01:51",
        }
    }

    enriched = upd_pls_tot.enrich_career_stats(
        career_stats_avg,
        career_enrichment,
        upd_pls_tot.CAREER_ENRICHMENT_AVERAGES,
        overwrite_existing=True,
    )

    assert enriched == {
        "avgToi": "18:00",
        "powerPlayTimeOnIcePerGame": "03:15",
        "shortHandedTimeOnIcePerGame": "01:51",
    }


# class utilsTests(SimpleTestCase):
#     def test_time_from_sec(self):
#         self.assertEqual(utils.time_from_sec(456546), '7609:06')
#         self.assertIsInstance(utils.time_from_sec(456546), str)

# EXAMPLE pytest monkeypatching

# contents of our original code file e.g. code.py
# import os


# def get_os_user_lower():
#     """Simple retrieval function.
#     Returns lowercase USER or raises OSError."""
#     username = os.getenv("USER")

#     if username is None:
#         raise OSError("USER environment is not set.")

#     return username.lower()
# ----------------------------------------------------------
# contents of our test file e.g. test_code.py
# import pytest


# @pytest.fixture
# def mock_env_user(monkeypatch):
#     monkeypatch.setenv("USER", "TestingUser")


# @pytest.fixture
# def mock_env_missing(monkeypatch):
#     monkeypatch.delenv("USER", raising=False)


# # notice the tests reference the fixtures for mocks
# def test_upper_to_lower(mock_env_user):
#     assert get_os_user_lower() == "testinguser"


# def test_raise_exception(mock_env_missing):
#     with pytest.raises(OSError):
#         _ = get_os_user_lower()
