"""Persistence contracts using Django's isolated test database, never the app DB."""

from copy import deepcopy

import pytest
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.core.management import call_command
from django.db import IntegrityError

from players import season_loading as loading
from players.management.commands import upd_pls, upd_pls_tot
from players.models import Goalie, Skater, Team
from players.season_stats import read_season_stats


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def stored_players():
    return {
        model.__name__: list(model.objects.order_by("nhl_id").values())
        for model in (Skater, Goalie)
    }


@pytest.fixture
def paged_reports(monkeypatch, requests_mock, season_report_data):
    """Reuse the report fixtures while exercising real HTTP pagination and assembly."""
    selected = {
        "skater": deepcopy(season_report_data["current_skater"]),
        "goalie": deepcopy(season_report_data["current_goalie"]),
    }
    for rows in [selected["skater"]["bios"], *selected["skater"]["reports"].values()]:
        second = deepcopy(rows[0])
        second["playerId"] = 9000002
        rows.append(second)
    selected["skater"]["bios"][1].update(
        skaterFullName="Second Synthetic Skater",
        lastName="Second",
        draftYear=2020,
        draftRound=4,
        draftOverall=100,
    )
    selected["skater"]["reports"]["summary"][1].update(goals=5, points=8)
    state = {"selected": selected, "observed": [], "failure": None}
    monkeypatch.setattr(loading, "REPORT_LIMIT", 1)
    monkeypatch.setattr(upd_pls, "pic_missing", lambda *args: False)
    requests_mock.get(upd_pls.URL_SCHEDULE_CALENDAR_NOW, json={"teams": [{"seasonId": 20262027}]})

    def response(request, context, player_type, report):
        state["observed"].append(stored_players())
        assert "seasonid=20262027" in request.qs["cayenneexp"][0]
        assert "gametypeid=2" in request.qs["cayenneexp"][0]
        assert request.timeout == loading.REPORT_TIMEOUT
        case = selected[player_type]
        rows = case["bios"] if report == loading.BIOS else case["reports"][report]
        start = int(request.qs["start"][0])
        size = int(request.qs["limit"][0])
        if player_type == "skater" and report == loading.BIOS and start == 1:
            if state["failure"] == "http":
                context.status_code = 503
                return {"error": "synthetic unavailable page"}
            if state["failure"] == "shape":
                return {"data": None, "total": len(rows)}
            if state["failure"] == "truncated":
                return {"data": [], "total": len(rows)}
            if state["failure"] == "overflow":
                return {"data": deepcopy(rows), "total": len(rows)}
        return {"data": deepcopy(rows[start : start + size]), "total": len(rows)}

    for player_type in (loading.GOALIE, loading.SKATER):
        for report in (loading.BIOS, *loading.REPORTS[player_type]):
            requests_mock.get(
                loading.REPORT_URL.format(player_type, report),
                json=lambda request, context, player_type=player_type, report=report: response(
                    request, context, player_type, report
                ),
            )
    return state


@pytest.fixture
def mock_reports(monkeypatch, season_report_data):
    selected = {"skater": season_report_data["current_skater"], "goalie": None}

    def fetch(report, player_type, session=None, season=None, player_id=None, team_id=None):
        case = selected[player_type]
        if case is None:
            return []
        if report == "bios":
            return deepcopy(case["bios"])
        if team_id is not None:
            team = {7: "BUF", 16: "COL"}[team_id]
            return deepcopy(case["team_reports"][team][report])
        return deepcopy(case["reports"][report])

    monkeypatch.setattr(loading, "fetch_report", fetch)
    monkeypatch.setattr(upd_pls, "get_season_id", lambda: "20262027")
    monkeypatch.setattr(upd_pls, "pic_missing", lambda *args: False)
    return selected


@pytest.fixture
def teams():
    return {
        "BUF": Team.objects.create(nhl_id=7, abbr="BUF", name="Buffalo Sabres"),
        "COL": Team.objects.create(nhl_id=16, abbr="COL", name="Colorado Avalanche"),
    }


@pytest.fixture
def old_skater(teams):
    history = {
        "season": "2025-26",
        "teamAbbr": "BUF",
        "gamesPlayed": 80,
        "goals": 20,
        "hits": 60,
        "customMetadata": "preserve",
    }
    return Skater.objects.create(
        nhl_id=9000001,
        name="Synthetic Skater",
        birth_date="2000-01-02",
        team=teams["BUF"],
        games=80,
        goals=20,
        goals_avg=0.25,
        hits=60,
        faceoff_wins=100,
        stats_season_id="20252026",
        sbs_stats=[history],
        sbs_stats_avg=[dict(history, goals=0.25)],
        career_stats={"goals": 20},
    )


def test_upd_pls_creates_season_preserves_history_and_is_repeatable(old_skater, mock_reports):
    history = deepcopy(old_skater.sbs_stats)
    historical_averages = deepcopy(old_skater.sbs_stats_avg)
    user = User.objects.create_user(username="loader-test-user")
    old_skater.favoriting.add(user)
    old_skater.comparing.add(user)
    old_pk = old_skater.pk
    absent = Skater.objects.create(
        nhl_id=9000002,
        name="Historical Only",
        birth_date="1990-01-01",
        games=80,
        goals=10,
        stats_season_id="20252026",
        sbs_stats=deepcopy(history),
    )

    upd_pls.Command().handle()

    old_skater.refresh_from_db()
    assert old_skater.pk == old_pk
    assert old_skater.stats_season_id == "20262027"
    assert (old_skater.games, old_skater.goals, old_skater.goals_avg) == (10, 2, 0.2)
    assert old_skater.sbs_stats[:1] == history
    assert old_skater.sbs_stats_avg[:1] == historical_averages
    assert old_skater.sbs_stats[-1]["goals"] == 2
    assert old_skater.sbs_stats_avg[-1]["hits"] == 0.8
    assert list(old_skater.favoriting.all()) == [user]
    assert list(old_skater.comparing.all()) == [user]
    absent.refresh_from_db()
    assert absent.stats_season_id == "20252026"
    assert absent.goals == 10
    first = deepcopy(old_skater.sbs_stats)

    upd_pls.Command().handle()

    old_skater.refresh_from_db()
    assert old_skater.sbs_stats == first
    assert Skater.objects.count() == 2


def test_missing_report_rows_clear_stale_values_in_same_season(
    old_skater, mock_reports, season_report_data
):
    upd_pls.Command().handle()
    mock_reports["skater"] = season_report_data["missing_enrichment"]

    upd_pls.Command().handle()

    old_skater.refresh_from_db()
    assert old_skater.goals == 0
    assert old_skater.hits is None
    assert old_skater.faceoff_wins is None
    assert old_skater.time_on_ice_pp == ""
    assert old_skater.sbs_stats[-1]["hits"] is None
    assert old_skater.sbs_stats[-1]["powerPlayTimeOnIce"] is None
    assert old_skater.sbs_stats_avg[-1]["hits"] is None


def test_traded_player_persists_combined_and_distinct_team_stats(
    old_skater, mock_reports, season_report_data
):
    mock_reports["skater"] = season_report_data["traded_skater"]
    # The live API retains combined team labels in numerically scoped reports.
    for reports in mock_reports["skater"]["team_reports"].values():
        for rows in reports.values():
            for row in rows:
                row["teamAbbrevs"] = "BUF,COL"

    upd_pls.Command().handle()

    old_skater.refresh_from_db()
    assert old_skater.goals == 4
    assert old_skater.multiteams_seasons == {"2026-27": 2}
    colorado = read_season_stats(
        old_skater.sbs_stats, "2026-27", player_type="skater", team_abbr="COL"
    )
    buffalo = read_season_stats(
        old_skater.sbs_stats, "2026-27", player_type="skater", team_abbr="BUF"
    )
    assert (colorado.totals["goals"], colorado.totals["hits"]) == (1, 8)
    assert (buffalo.totals["goals"], buffalo.totals["hits"]) == (3, 6)


def test_upd_pls_can_create_goalie_without_a_full_refresh(teams, mock_reports, season_report_data):
    mock_reports["goalie"] = season_report_data["current_goalie"]
    mock_reports["skater"] = None

    upd_pls.Command().handle()

    goalie = Goalie.objects.get(nhl_id=9000001)
    assert (goalie.games, goalie.wins, goalie.saves) == (4, 2, 90)
    assert goalie.stats_season_id == "20262027"
    assert goalie.sbs_stats[0]["savePctg"] == 0.9
    assert goalie.sbs_stats[0]["saves"] == 90


def test_report_interruption_leaves_database_untouched(
    old_skater, mock_reports, season_report_data, monkeypatch
):
    mock_reports["goalie"] = season_report_data["current_goalie"]
    original = loading.fetch_report

    def fail_last_report(report, *args, **kwargs):
        if report == "timeonice":
            raise CommandError("upstream unavailable")
        return original(report, *args, **kwargs)

    monkeypatch.setattr(loading, "fetch_report", fail_last_report)
    with pytest.raises(CommandError, match="upstream"):
        upd_pls.Command().handle()

    old_skater.refresh_from_db()
    assert old_skater.stats_season_id == "20252026"
    assert old_skater.goals == 20
    assert len(old_skater.sbs_stats) == 1
    assert Goalie.objects.count() == 0


def test_database_failure_rolls_back_every_player_in_publication(
    old_skater, mock_reports, season_report_data, monkeypatch
):
    mock_reports["goalie"] = season_report_data["current_goalie"]
    original = upd_pls.import_player

    def fail_skater(bio, fresh, player_type):
        if player_type == "skater":
            raise IntegrityError("simulated persistence failure")
        return original(bio, fresh, player_type)

    monkeypatch.setattr(upd_pls, "import_player", fail_skater)
    with pytest.raises(IntegrityError, match="persistence"):
        upd_pls.Command().handle()

    assert Goalie.objects.count() == 0
    old_skater.refresh_from_db()
    assert old_skater.stats_season_id == "20252026"
    assert old_skater.goals == 20


def test_current_mode_creates_missing_season_without_snapshot_or_landing(
    old_skater, mock_reports, monkeypatch
):
    monkeypatch.setattr(upd_pls_tot, "get_skater_career_enrichment", lambda *args: {})
    monkeypatch.setattr(upd_pls_tot, "get_response", lambda *args: pytest.fail("landing called"))

    upd_pls_tot.apply_current_mode_to_skater(old_skater, season="20262027")

    old_skater.refresh_from_db()
    assert old_skater.stats_season_id == "20262027"
    assert old_skater.goals == 2
    assert old_skater.sbs_stats[-1]["goals"] == 2
    assert old_skater.sbs_stats[-1]["hits"] == 8
    assert old_skater.sbs_stats_avg[-1]["hits"] == 0.8


def test_current_command_reuses_bulk_season_reports(old_skater, mock_reports, monkeypatch):
    monkeypatch.setattr(upd_pls_tot, "get_all_players", lambda: [old_skater])
    monkeypatch.setattr(upd_pls_tot, "get_skater_career_enrichment", lambda *args: {})
    monkeypatch.setattr(
        upd_pls_tot, "get_report_season_rows", lambda *args: pytest.fail("per-player fetch called")
    )

    upd_pls_tot.run_current_mode()

    old_skater.refresh_from_db()
    assert old_skater.goals == 2
    assert old_skater.stats_season_id == "20262027"


def test_full_refresh_uses_team_scoped_reports_and_preserves_unreturned_history(
    old_skater, mock_reports, season_report_data, monkeypatch
):
    mock_reports["skater"] = season_report_data["traded_skater"]
    monkeypatch.setattr(upd_pls_tot, "get_skater_career_enrichment", lambda *args: {})
    data = {
        "firstName": {"default": "Synthetic"},
        "heightInInches": 70,
        "heightInCentimeters": 178,
        "weightInPounds": 200,
        "weightInKilograms": 91,
        "position": "C",
        "careerTotals": {"regularSeason": {"gamesPlayed": 90, "goals": 24}},
        "seasonTotals": [],
    }

    upd_pls_tot.import_player(data, old_skater)

    old_skater.refresh_from_db()
    assert old_skater.sbs_stats[0]["season"] == "2025-26"
    assert old_skater.sbs_stats[0]["customMetadata"] == "preserve"
    assert old_skater.career_stats["goals"] == 24
    assert old_skater.goals == 4
    assert old_skater.multiteams_seasons == {"2026-27": 2}
    colorado = read_season_stats(
        old_skater.sbs_stats, "2026-27", player_type="skater", team_abbr="COL"
    )
    assert colorado.totals["hits"] == 8


def test_paginated_command_publishes_both_player_types_and_replays_without_duplicates(
    old_skater, paged_reports, requests_mock
):
    before = stored_players()
    history = deepcopy(old_skater.sbs_stats)

    call_command("upd_pls")

    assert paged_reports["observed"]
    assert all(snapshot == before for snapshot in paged_reports["observed"])
    old_skater.refresh_from_db()
    assert old_skater.sbs_stats[:1] == history
    assert old_skater.stats_season_id == "20262027"
    assert old_skater.goals == 2
    second = Skater.objects.get(nhl_id=9000002)
    assert (second.name, second.games, second.goals, second.points) == (
        "Second Synthetic Skater",
        10,
        5,
        8,
    )
    assert (second.draft_year, second.draft_round, second.draft_number) == (2020, 4, 100)
    goalie = Goalie.objects.get(nhl_id=9000001)
    assert (goalie.games, goalie.wins, goalie.saves, goalie.position_abbr) == (4, 2, 90, "G")
    assert goalie.stats_season_id == "20262027"
    for report in (loading.BIOS, *loading.REPORTS[loading.SKATER]):
        pages = [
            item.qs["start"]
            for item in requests_mock.request_history
            if item.path == "/stats/rest/en/skater/" + report
        ]
        assert pages == [["0"], ["1"]]
    published = stored_players()
    paged_reports["observed"].clear()

    call_command("upd_pls")

    assert stored_players() == published
    assert all(snapshot == published for snapshot in paged_reports["observed"])


@pytest.mark.parametrize(
    "invalid, message",
    [
        ("duplicate_bio", "Bios report does not cover summary players uniquely"),
        ("missing_bio", "Bios report does not cover summary players uniquely"),
        ("bio_games", "Bios and summary disagree on gamesPlayed"),
        ("duplicate_summary", "Ambiguous summary rows"),
        ("duplicate_enrichment", "Ambiguous realtime rows"),
    ],
)
def test_paginated_validation_failure_does_not_publish_staged_goalies_or_skaters(
    old_skater, paged_reports, invalid, message
):
    case = paged_reports["selected"]["skater"]
    if invalid == "duplicate_bio":
        case["bios"].append(deepcopy(case["bios"][-1]))
    elif invalid == "missing_bio":
        case["bios"].pop()
    elif invalid == "bio_games":
        case["bios"][-1]["gamesPlayed"] += 1
    else:
        report = loading.SUMMARY if invalid == "duplicate_summary" else loading.REALTIME
        case["reports"][report].append(deepcopy(case["reports"][report][-1]))
    before = stored_players()

    with pytest.raises(CommandError, match=message):
        call_command("upd_pls")

    assert stored_players() == before
    assert paged_reports["observed"]
    assert all(snapshot == before for snapshot in paged_reports["observed"])


@pytest.mark.parametrize("failure", ["http", "shape", "truncated", "overflow"])
def test_bad_later_bios_page_never_publishes_a_partial_roster(
    old_skater, paged_reports, requests_mock, failure
):
    paged_reports["failure"] = failure
    before = stored_players()
    message = {
        "http": "Failed skater bios report at start=1",
        "shape": "Failed skater bios report at start=1",
        "truncated": "pagination ended before",
        "overflow": "more rows than its declared total",
    }[failure]

    with pytest.raises(CommandError, match=message):
        call_command("upd_pls")

    assert stored_players() == before
    assert all(snapshot == before for snapshot in paged_reports["observed"])
    pages = [
        request.qs["start"]
        for request in requests_mock.request_history
        if request.path == "/stats/rest/en/skater/bios"
    ]
    attempts = loading.REPORT_ATTEMPTS if failure in {"http", "shape"} else 1
    assert pages == [["0"]] + [["1"]] * attempts


def test_bio_without_summary_leaves_existing_player_and_season_marker_untouched(
    old_skater, paged_reports
):
    case = paged_reports["selected"]["skater"]
    case["bios"] = case["bios"][:1]
    case["bios"][0]["gamesPlayed"] = 0
    for report in case["reports"]:
        case["reports"][report] = []
    before = list(Skater.objects.order_by("nhl_id").values())

    call_command("upd_pls")

    assert list(Skater.objects.order_by("nhl_id").values()) == before
    assert Skater.objects.count() == 1
    assert Goalie.objects.get(nhl_id=9000001).stats_season_id == "20262027"
