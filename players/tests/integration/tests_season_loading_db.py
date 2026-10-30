"""Persistence contracts using Django's isolated test database, never the app DB."""

from copy import deepcopy

import pytest
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.db import IntegrityError

from players import season_loading as loading
from players.management.commands import upd_pls, upd_pls_tot
from players.models import Goalie, Skater, Team
from players.season_stats import read_season_stats


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


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
