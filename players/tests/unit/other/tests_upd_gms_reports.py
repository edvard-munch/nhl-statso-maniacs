from players.management.commands import upd_gms


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
