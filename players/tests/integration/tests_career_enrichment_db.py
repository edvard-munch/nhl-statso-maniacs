"""Real career persistence from mocked aggregate NHL HTTP responses."""

from copy import deepcopy
import json
from types import SimpleNamespace

from django.core.management import call_command
from django.core.management.base import CommandError
import pytest
import requests

from players import season_loading as loading
from players.management.commands import upd_pls, upd_pls_tot as totals
from players.models import Goalie, Skater, Team


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(params=["skater", "goalie"])
def career_player(request, requests_mock, season_report_data, monkeypatch):
    kind = request.param
    model = Skater if kind == "skater" else Goalie
    team = Team.objects.create(nhl_id=7, abbr="BUF", name="Buffalo")
    career = (
        {"gamesPlayed": 80, "goals": 20, "hits": 0, "blocked": None, "faceoffsWon": None}
        if kind == "skater"
        else {"gamesPlayed": 80, "wins": 30, "saves": 999, "savePctg": 0.8}
    )
    career["custom"] = "keep"
    history = {"season": "2025-26", "teamAbbr": "BUF", "gamesPlayed": 80, "custom": "history"}
    extra = (
        {
            "career_stats_avg": {"hits": 99, "custom": "average"},
            "sbs_stats_avg": [deepcopy(history)],
        }
        if kind == "skater"
        else {}
    )
    player = model.objects.create(
        nhl_id=9000001,
        name="Career Fixture",
        birth_date="2000-01-02",
        team=team,
        games=80,
        stats_season_id="20252026",
        sbs_stats=[history],
        career_stats=career,
        **extra,
    )
    case = deepcopy(season_report_data["current_" + kind])
    state = dict(failure=None, observed=[], aggregate_requests=[])
    aggregate = (
        {
            "realtime": [{"gamesPlayed": 80, "hits": 400, "blockedShots": 100}],
            "faceoffwins": [{"gamesPlayed": 80, "totalFaceoffWins": 0}],
            "timeonice": [{"ppTimeOnIcePerGame": 125, "shTimeOnIcePerGame": 0}],
        }
        if kind == "skater"
        else {
            "summary": [
                {
                    "gamesPlayed": 100,
                    "wins": 40,
                    "losses": 45,
                    "otLosses": 15,
                    "goalsAgainstAverage": 2.5,
                    "savePct": 0.91,
                    "saves": 2000,
                    "shutouts": 0,
                }
            ]
        }
    )
    monkeypatch.setattr(upd_pls, "pic_missing", lambda *args: False)
    requests_mock.get(upd_pls.URL_SCHEDULE_CALENDAR_NOW, json={"teams": [{"seasonId": 20262027}]})
    landing = dict(
        firstName={"default": "Career"},
        heightInInches=70,
        heightInCentimeters=178,
        weightInPounds=200,
        weightInKilograms=91,
        position="C" if kind == "skater" else "G",
        careerTotals={
            "regularSeason": {
                "gamesPlayed": 100,
                "goals": 40,
                "hits": 7,
                "shotsAgainst": 1000,
                "goalsAgainst": 100,
            }
        },
    )
    landing_mock = requests_mock.get(totals.PLAYER_ENDPOINT_URL.format(player.nhl_id), json=landing)

    def response(request, context, report, player_type):
        if request.qs["isaggregate"] == ["true"]:
            assert player_type == kind
            assert request.qs["isgame"] == ["false"]
            assert request.qs["limit"] == [str(totals.STATS_REST_LIMIT)]
            assert request.qs["start"] == ["0"]
            assert request.qs["cayenneexp"] == ["gametypeid=2 and playerid=9000001"]
            assert request.timeout == totals.STATS_REST_TIMEOUT
            state["aggregate_requests"].append(report)
            state["observed"].append(model.objects.values().get(pk=player.pk))
            failure = state["failure"]
            if failure in ("http", "rate_limit"):
                context.status_code = 503 if failure == "http" else 429
                return "unavailable"
            if failure == "timeout":
                raise requests.Timeout("synthetic career timeout")
            if failure == "json":
                return "not JSON"
            if failure == "shape":
                return json.dumps([])
            if failure == "null":
                return json.dumps({"data": None})
            if failure == "row":
                return json.dumps({"data": [None]})
            if failure == "missing":
                return json.dumps({})
            return json.dumps({"data": [] if failure == "empty" else aggregate[report]})
        rows = case["reports"][report] if player_type == kind else []
        return json.dumps({"data": deepcopy(rows), "total": len(rows)})

    for player_type in (loading.GOALIE, loading.SKATER):
        for report in loading.REPORTS[player_type]:
            requests_mock.get(
                loading.REPORT_URL.format(player_type, report),
                text=lambda request, context, report=report, player_type=player_type: response(
                    request, context, report, player_type
                ),
            )
    return SimpleNamespace(
        player=player,
        model=model,
        kind=kind,
        state=state,
        aggregate=aggregate,
        landing=landing,
        landing_mock=landing_mock,
    )


def test_current_career_http_enrichment_precedence_and_replay(career_player):
    fixture = career_player
    before = fixture.model.objects.values().get(pk=fixture.player.pk)
    for _ in range(2):
        fixture.state["observed"].clear()
        current = fixture.model.objects.values().get(pk=fixture.player.pk)
        call_command("upd_pls_tot", mode="current")
        assert all(row == current for row in fixture.state["observed"])
        player = fixture.model.objects.get(pk=fixture.player.pk)
        assert player.career_stats["custom"] == "keep"
        assert player.sbs_stats[0] == before["sbs_stats"][0]
        assert player.stats_season_id == "20262027"
        if fixture.kind == "skater":
            assert player.career_stats["hits"] == 0  # Existing total, including zero, wins.
            assert player.career_stats["blocked"] == 100
            assert player.career_stats["faceoffsWon"] == 0
            assert player.career_stats_avg["hits"] == 5
            assert player.career_stats_avg["blocked"] == 1.25
            assert player.career_stats_avg["faceoffsWon"] == 0
            assert player.career_stats_avg["powerPlayTimeOnIcePerGame"] == "02:05"
            assert player.career_stats_avg["shortHandedTimeOnIcePerGame"] == "00:00"
            assert player.career_stats_avg["custom"] == "average"
            assert player.sbs_stats[-1]["hits"] == 8
        else:
            assert (
                player.career_stats["gamesPlayed"],
                player.career_stats["wins"],
                player.career_stats["saves"],
                player.career_stats["shutouts"],
            ) == (100, 40, 2000, 0)
            assert (player.career_stats["goalsAgainstAvg"], player.career_stats["savePctg"]) == (
                2.5,
                0.91,
            )
            assert player.sbs_stats[-1]["saves"] == 90
    assert fixture.landing_mock.call_count == 0


def test_full_mode_landing_precedence_and_actual_enrichment_requests(career_player):
    fixture = career_player
    call_command("upd_pls_tot", mode="full")
    player = fixture.model.objects.get(pk=fixture.player.pk)
    assert player.career_stats["gamesPlayed"] == 100
    if fixture.kind == "skater":
        assert set(fixture.state["aggregate_requests"]) == {"realtime", "faceoffwins", "timeonice"}
        assert player.career_stats["hits"] == 7  # Landing total wins over aggregate 400.
        assert player.career_stats["blocked"] == 100
        assert player.career_stats_avg["hits"] == 5  # Aggregate average wins over 7/100.
        assert player.career_stats_avg["goals"] == 0.4
    else:
        assert fixture.state["aggregate_requests"] == []  # Full goalie totals use landing.
        assert player.career_stats["saves"] == 900
    assert fixture.landing_mock.call_count == 1
    assert player.sbs_stats[0]["custom"] == "history"


@pytest.mark.parametrize("failure", ["empty", "http", "rate_limit", "timeout"])
def test_unavailable_optional_career_data_preserves_saved_values(career_player, failure):
    fixture = career_player
    before = deepcopy(fixture.player.career_stats)
    fixture.state["failure"] = failure
    if failure == "rate_limit":
        stored = fixture.model.objects.values().get(pk=fixture.player.pk)
        with pytest.raises(CommandError, match="after 3 attempt"):
            call_command("upd_pls_tot", mode="current")
        assert fixture.model.objects.values().get(pk=fixture.player.pk) == stored
        assert len(fixture.state["aggregate_requests"]) == 3
        return
    call_command("upd_pls_tot", mode="current")
    fixture.player.refresh_from_db()
    assert fixture.player.career_stats == before
    if fixture.kind == "skater":
        assert fixture.player.career_stats_avg == {"hits": 99, "custom": "average"}
    assert fixture.player.stats_season_id == "20262027"
    assert fixture.player.sbs_stats[-1]["gamesPlayed"] == (10 if fixture.kind == "skater" else 4)
    reports = 3 if fixture.kind == "skater" else 1
    attempts = 1 if failure == "empty" else 3
    assert len(fixture.state["aggregate_requests"]) == reports * attempts


@pytest.mark.parametrize("failure", ["json", "shape", "null", "row", "missing"])
def test_malformed_career_response_aborts_before_player_save(career_player, failure):
    fixture = career_player
    fixture.state["failure"] = failure
    before = fixture.model.objects.values().get(pk=fixture.player.pk)
    with pytest.raises(CommandError, match="Invalid career report .* for player 9000001"):
        call_command("upd_pls_tot", mode="current")
    assert fixture.model.objects.values().get(pk=fixture.player.pk) == before


def test_partial_career_row_never_erases_saved_values(career_player):
    fixture = career_player
    if fixture.kind == "skater":
        fixture.aggregate["realtime"] = [{"gamesPlayed": 0, "hits": None, "blockedShots": 0}]
        fixture.aggregate["faceoffwins"] = [{"gamesPlayed": 0, "totalFaceoffWins": None}]
        fixture.aggregate["timeonice"] = [{"ppTimeOnIcePerGame": None, "shTimeOnIcePerGame": 0}]
    else:
        fixture.aggregate["summary"] = [{"wins": None, "saves": 0, "shutouts": 0}]
    call_command("upd_pls_tot", mode="current")
    fixture.player.refresh_from_db()
    career = fixture.player.career_stats
    if fixture.kind == "skater":
        assert career["hits"] == 0
        assert career["blocked"] == 0
        assert fixture.player.career_stats_avg["hits"] == 99  # Undefined per-game value not zero.
        assert fixture.player.career_stats_avg["shortHandedTimeOnIcePerGame"] == "00:00"
    else:
        assert (career["gamesPlayed"], career["wins"], career["saves"], career["shutouts"]) == (
            80,
            30,
            0,
            0,
        )
        assert career["savePctg"] == 0.8
