"""Small live contracts for the report readers; no publication or database access."""

import pytest

from players import season_loading
from players.management.commands import upd_pls_tot


pytestmark = [pytest.mark.integration, pytest.mark.external]

BIOS_FIELDS = {
    "playerId",
    "birthDate",
    "firstSeasonForGameType",
    "birthCountryCode",
    "nationalityCode",
    "height",
    "weight",
}
SKATER_FIELDS = {
    "summary": set(season_loading.SUMMARY_SKATER_FIELDS.values()) | {"timeOnIcePerGame"},
    "realtime": {"hits", "blockedShots"},
    "faceoffwins": {"totalFaceoffWins"},
    "timeonice": {"ppTimeOnIcePerGame", "shTimeOnIcePerGame"},
}


@pytest.mark.parametrize(
    "player_type, report",
    [
        ("goalie", "bios"),
        ("goalie", "summary"),
        ("skater", "bios"),
        ("skater", "summary"),
        ("skater", "realtime"),
        ("skater", "faceoffwins"),
        ("skater", "timeonice"),
    ],
)
def test_season_report_reader_contract(player_type, report, live_reference, live_session):
    player_id = live_reference["players"][player_type]
    rows = season_loading.fetch_report(
        report,
        player_type,
        session=live_session,
        season=live_reference["season"],
        player_id=player_id,
    )
    assert rows, f"Empty {player_type} {report} for reference player {player_id}"
    if report == "bios":
        required = BIOS_FIELDS | {player_type + "FullName"}
        if player_type == "skater":
            required |= {"positionCode"}
    else:
        required = {"playerId", "seasonId", "gamesPlayed", "teamAbbrevs"}
        required |= (
            SKATER_FIELDS[report]
            if player_type == "skater"
            else set(season_loading.SUMMARY_GOALIE_FIELDS.values())
        )
    for row in rows:
        assert required <= row.keys(), f"Missing {required - row.keys()} in {player_type} {report}"
        assert row["playerId"] == player_id
        if report != "bios":
            assert str(row["seasonId"]) == live_reference["season"]
            assert row["gamesPlayed"] > 0


@pytest.mark.parametrize(
    "player_type, report, fields",
    [
        ("skater", "realtime", {"hits", "blockedShots", "gamesPlayed"}),
        ("skater", "faceoffwins", {"totalFaceoffWins", "gamesPlayed"}),
        ("skater", "timeonice", {"ppTimeOnIcePerGame", "shTimeOnIcePerGame", "gamesPlayed"}),
        ("goalie", "summary", set(season_loading.SUMMARY_GOALIE_FIELDS.values())),
    ],
)
def test_career_report_reader_contract(player_type, report, fields, live_reference, live_session):
    reader = (
        upd_pls_tot.get_stats_rest_rows
        if player_type == "skater"
        else upd_pls_tot.get_goalie_stats_rest_rows
    )
    player_id = live_reference["players"][player_type]
    rows = reader(report, player_id, session=live_session, aggregate=True)
    assert rows, f"Empty career {player_type} {report}; optional endpoint may be unavailable"
    for row in rows:
        assert fields | {"playerId"} <= row.keys()
        assert row["playerId"] == player_id
        assert row["gamesPlayed"] > 0
