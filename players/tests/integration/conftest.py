"""Lazy, read-only fixtures used only by explicitly selected live API checks."""

from time import monotonic, sleep

import pytest
import requests


LIVE_REQUEST_INTERVAL = 1.0
REFERENCE_SEASON = "20232024"
REFERENCE_GAME_ID = 2023020001
REFERENCE_GAME_DATE = "2023-10-10"
REFERENCE_PLAYERS = {"skater": 8478402, "goalie": 8476883}


@pytest.fixture(scope="session")
def live_reference():
    return {
        "season": REFERENCE_SEASON,
        "game_id": REFERENCE_GAME_ID,
        "date": REFERENCE_GAME_DATE,
        "players": dict(REFERENCE_PLAYERS),
    }


@pytest.fixture(scope="session")
def live_session():
    class PacedReadOnlySession(requests.Session):
        last_request = None

        def request(self, method, url, **kwargs):
            assert method.upper() == "GET", "Live checks must be read-only"
            if self.last_request is not None:
                sleep(max(0, LIVE_REQUEST_INTERVAL - (monotonic() - self.last_request)))
            self.last_request = monotonic()
            return super().request(method, url, **kwargs)

    with PacedReadOnlySession() as session:
        yield session


@pytest.fixture(scope="session")
def live_boxscore(live_reference, live_session):
    from players.management.commands import upd_gms

    return upd_gms.get_game_data(
        live_reference["game_id"], upd_gms.URL_BOXSCORE, session=live_session
    )


@pytest.fixture(scope="session")
def live_report_links(live_reference, live_session):
    from players.management.commands import upd_gms

    return upd_gms.get_game_report_links(live_reference["game_id"], session=live_session)
