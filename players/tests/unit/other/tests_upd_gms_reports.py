from players.management.commands import upd_gms
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "files"


def load_fixture(name):
    return (FIXTURES_DIR / name).read_text()


def test_get_game_report_links_extracts_supported_links(requests_mock):
    game_id = 2025020001
    url = upd_gms.URL_RIGHT_RAIL.format(game_id)
    payload = {
        "gameReports": {
            "eventSummary": "https://www.nhl.com/scores/htmlreports/20252026/ES020001.HTM",
            "faceoffSummary": "https://www.nhl.com/scores/htmlreports/20252026/FS020001.HTM",
            "toiAway": "https://www.nhl.com/scores/htmlreports/20252026/TV020001.HTM",
            "toiHome": "https://www.nhl.com/scores/htmlreports/20252026/TH020001.HTM",
            "playByPlay": "https://www.nhl.com/scores/htmlreports/20252026/PL020001.HTM",
        }
    }
    requests_mock.get(url, json=payload)

    assert upd_gms.get_game_report_links(game_id) == {
        "eventSummary": "https://www.nhl.com/scores/htmlreports/20252026/ES020001.HTM",
        "faceoffSummary": "https://www.nhl.com/scores/htmlreports/20252026/FS020001.HTM",
        "toiAway": "https://www.nhl.com/scores/htmlreports/20252026/TV020001.HTM",
        "toiHome": "https://www.nhl.com/scores/htmlreports/20252026/TH020001.HTM",
    }


def test_extract_game_report_links_missing_or_invalid_fallback_to_none():
    right_rail_data = {
        "gameReports": {
            "eventSummary": "",
            "faceoffSummary": "www.nhl.com/no-scheme",
            "toiAway": None,
            "toiHome": "https://www.nhl.com/scores/htmlreports/20252026/TH020001.HTM",
        }
    }

    assert upd_gms.extract_game_report_links(right_rail_data) == {
        "eventSummary": None,
        "faceoffSummary": None,
        "toiAway": None,
        "toiHome": "https://www.nhl.com/scores/htmlreports/20252026/TH020001.HTM",
    }

    assert upd_gms.extract_game_report_links({}) == {
        "eventSummary": None,
        "faceoffSummary": None,
        "toiAway": None,
        "toiHome": None,
    }


def test_parse_event_summary_report_extracts_ppp_shp_and_skips_missing_player_row():
    report_html = load_fixture("report_event_summary.html")

    assert upd_gms.parse_event_summary_report(report_html) == {
        98: {"powerPlayPoints": 2, "shPoints": 0},
        59: {"powerPlayPoints": None, "shPoints": 1},
    }


def test_parse_faceoff_summary_report_extracts_faceoff_wins():
    report_html = load_fixture("report_faceoff_summary.html")

    assert upd_gms.parse_faceoff_summary_report(report_html) == {
        98: {"faceoffs": 12},
        16: {"faceoffs": 9},
    }


def test_parse_toi_report_parses_times_and_handles_empty_or_invalid_values():
    report_html = load_fixture("report_toi.html")

    assert upd_gms.parse_toi_report(report_html) == {
        98: {"powerPlayToi": "04:31", "shorthandedToi": "01:05"},
        59: {"powerPlayToi": "", "shorthandedToi": ""},
        16: {"powerPlayToi": "3:10", "shorthandedToi": "0:44"},
    }
