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


def test_parse_faceoff_summary_report_fallback_player_blocks():
    report_html = """
    <table>
      <tr><td>13 C REINHART, SAM</td></tr>
      <tr><td>Strength</td><td>Off.</td><td>Def.</td><td>Neu.</td><td>TOT</td></tr>
      <tr><td>TOT</td><td>4-6/67%</td><td>0-1/0%</td><td>1-2/50%</td><td>5-9/56%</td></tr>
      <tr><td>15 C LUNDELL, ANTON</td></tr>
      <tr><td>TOT</td><td>1-1/100%</td><td>2-4/50%</td><td>0-0/0%</td><td>3-5/60%</td></tr>
    </table>
    """

    assert upd_gms.parse_faceoff_summary_report(report_html) == {
        13: {"faceoffs": 5},
        15: {"faceoffs": 3},
    }


def test_parse_toi_report_fallback_player_blocks():
    report_html = """
    <table>
      <tr><td>13 REINHART, SAM</td></tr>
      <tr><td>Per</td><td>SHF</td><td>AVG</td><td>TOI</td><td>EV TOT</td><td>PP TOT</td><td>SH TOT</td></tr>
      <tr><td>1</td><td>9</td><td>00:50</td><td>07:34</td><td>05:06</td><td>01:20</td><td>01:08</td></tr>
      <tr><td>TOT</td><td>25</td><td>00:54</td><td>22:31</td><td>16:05</td><td>05:10</td><td>01:16</td></tr>
      <tr><td>15 LUNDELL, ANTON</td></tr>
      <tr><td>TOT</td><td>24</td><td>00:43</td><td>17:19</td><td>12:28</td><td>03:37</td><td>01:14</td></tr>
    </table>
    """

    assert upd_gms.parse_toi_report(report_html) == {
        13: {"powerPlayToi": "05:10", "shorthandedToi": "01:16"},
        15: {"powerPlayToi": "03:37", "shorthandedToi": "01:14"},
    }
