import json
from pathlib import Path

import pytest


SEASON_FIXTURES_PATH = Path(__file__).parent / "fixtures" / "season_stats.json"


@pytest.fixture
def season_stats_data():
    """Fresh synthetic API inputs and expected values for each test."""
    return json.loads(SEASON_FIXTURES_PATH.read_text())


@pytest.fixture
def season_report_data():
    """Synthetic stats/rest inputs corresponding to the season statistics cases."""
    return json.loads((SEASON_FIXTURES_PATH.parent / "season_reports.json").read_text())
