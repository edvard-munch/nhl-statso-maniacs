"""Biography and local flag contracts through real player publication and replay."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.management import call_command
import pytest

from players import season_loading as loading
from players.management.commands import upd_pls
from players.models import Goalie, Skater, Team


pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(params=["skater", "goalie"])
def metadata_reports(request, requests_mock, season_report_data, settings, tmp_path, monkeypatch):
    player_type = request.param
    case = deepcopy(season_report_data["current_" + player_type])
    settings.MEDIA_ROOT = str(tmp_path / "media")
    flags = tmp_path / "media" / "flags"
    flags.mkdir(parents=True)
    monkeypatch.setattr(upd_pls, "TODAY", date(2026, 3, 1))
    monkeypatch.setattr(upd_pls, "UNKNOWN_COUNTRY_CODES", set())
    teams = {
        abbr: Team.objects.create(nhl_id=nhl_id, abbr=abbr, name=abbr)
        for nhl_id, abbr in [(7, "BUF"), (16, "COL")]
    }
    requests_mock.get(upd_pls.URL_SCHEDULE_CALENDAR_NOW, json={"teams": [{"seasonId": 20262027}]})

    def response(request, context, report, requested_type):
        assert "seasonid=20262027" in request.qs["cayenneexp"][0]
        rows = []
        if requested_type == player_type:
            rows = case["bios"] if report == loading.BIOS else case["reports"][report]
        return {"data": deepcopy(rows), "total": len(rows)}

    for requested_type in (loading.GOALIE, loading.SKATER):
        for report in (loading.BIOS, *loading.REPORTS[requested_type]):
            requests_mock.get(
                loading.REPORT_URL.format(requested_type, report),
                json=lambda request, context, report=report, requested_type=requested_type: (
                    response(request, context, report, requested_type)
                ),
            )
    return SimpleNamespace(
        case=case,
        bio=case["bios"][0],
        flags=flags,
        teams=teams,
        model=Skater if player_type == "skater" else Goalie,
        player_type=player_type,
    )


def publish(fixture):
    call_command("upd_pls")
    return fixture.model.objects.get(nhl_id=fixture.bio["playerId"])


def test_biography_refresh_preserves_identity_and_unreported_metadata(metadata_reports):
    fixture = metadata_reports
    fixture.bio.update(draftYear=2018, draftRound=2, draftOverall=40)
    player = publish(fixture)
    original_pk, original_slug = player.pk, player.slug
    user = User.objects.create_user(username="metadata-owner")
    player.favoriting.add(user)
    player.comparing.add(user)
    player.height = "6'0"
    player.roster_status = "I"
    player.rookie = True
    player.gamelog_stats = {"2025-10-01": {"goals": 2, "custom": "keep"}}
    player.save()
    fixture.bio.update(
        lastName="Renamed",
        birthCity=None,
        birthStateProvinceCode="ON",
        currentTeamAbbrev="COL",
        nationalityCode="USA",
    )
    fixture.bio["skaterFullName" if fixture.player_type == "skater" else "goalieFullName"] = (
        "Renamed Player"
    )
    if fixture.player_type == "skater":
        fixture.bio["positionCode"] = "R"

    player = publish(fixture)

    assert (player.pk, player.slug) == (original_pk, original_slug)
    assert (player.name, player.last_name, player.birth_city, player.birth_state) == (
        "Renamed Player",
        "Renamed",
        "",
        "ON",
    )
    assert player.birth_date == date(2000, 1, 2)
    assert player.age == 26
    assert player.nhl_debut == "2025-26"
    assert (player.birth_country, player.birth_country_abbr) == ("Canada", "CAN")
    assert (player.nation, player.nation_abbr) == ("USA", "USA")
    assert player.team_id == fixture.teams["COL"].pk
    assert (player.position_abbr, player.position_name) == (
        ("RW", "Right winger") if fixture.player_type == "skater" else ("G", "Goalie")
    )
    assert (player.draft_year, player.draft_round, player.draft_number) == (2018, 2, 40)
    assert (player.height, player.roster_status, player.rookie) == ("6'0", "I", True)
    assert player.gamelog_stats == {"2025-10-01": {"goals": 2, "custom": "keep"}}
    assert list(player.favoriting.all()) == [user]
    assert list(player.comparing.all()) == [user]
    # Current roster changes do not relabel the report's season contribution.
    assert player.sbs_stats[-1]["teamAbbr"] == "BUF"
    assert fixture.model.objects.count() == 1


@pytest.mark.parametrize("nationality", [None, "", "omitted"])
def test_missing_nationality_uses_birth_country(metadata_reports, nationality):
    fixture = metadata_reports
    fixture.bio["birthCountryCode"] = "SWE"
    if nationality == "omitted":
        fixture.bio.pop("nationalityCode")
    else:
        fixture.bio["nationalityCode"] = nationality
    player = publish(fixture)
    assert (player.nation, player.nation_abbr) == ("Sweden", "SWE")
    assert (player.birth_country, player.birth_country_abbr) == ("Sweden", "SWE")


def test_absent_draft_report_preserves_saved_draft_history(metadata_reports):
    fixture = metadata_reports
    fixture.bio.update(draftYear=2018, draftRound=2, draftOverall=40)
    player = publish(fixture)
    for key in ("draftYear", "draftRound", "draftOverall"):
        fixture.bio.pop(key)
    player = publish(fixture)
    assert (player.draft_year, player.draft_round, player.draft_number) == (2018, 2, 40)
    # A later explicit draft correction still replaces those values.
    fixture.bio.update(draftYear=2019, draftRound=3, draftOverall=70)
    player = publish(fixture)
    assert (player.draft_year, player.draft_round, player.draft_number) == (2019, 3, 70)


def test_cached_flags_attach_once_and_follow_nationality_change(metadata_reports, monkeypatch):
    fixture = metadata_reports
    for code in ("CAN", "USA"):
        (fixture.flags / (code + ".jpg")).write_bytes(b"cached flag; no image decoding needed")
    original = upd_pls.upload_flag
    calls = []

    def attach(player, name):
        calls.append((player.pk, name))
        original(player, name)

    monkeypatch.setattr(upd_pls, "upload_flag", attach)
    player = publish(fixture)
    assert player.nation_flag.name == "flags/CAN.jpg"
    publish(fixture)
    assert calls == [(player.pk, "CAN.jpg")]
    fixture.bio["nationalityCode"] = "USA"
    player = publish(fixture)
    assert player.nation_flag.name == "flags/USA.jpg"
    publish(fixture)
    assert calls == [(player.pk, "CAN.jpg"), (player.pk, "USA.jpg")]
    assert sorted(p.name for p in fixture.flags.iterdir()) == ["CAN.jpg", "USA.jpg"]


def test_missing_flag_does_not_block_stats_and_later_cache_recovers(metadata_reports, capsys):
    fixture = metadata_reports
    player = publish(fixture)
    assert player.nation_flag.name == "flag.png"
    assert player.stats_season_id == "20262027"
    assert player.sbs_stats[-1]["gamesPlayed"] == (10 if fixture.player_type == "skater" else 4)
    assert "has no flag yet" in capsys.readouterr().out
    (fixture.flags / "CAN.jpg").write_bytes(b"later cached flag")
    recovered = publish(fixture)
    assert recovered.pk == player.pk
    assert recovered.nation_flag.name == "flags/CAN.jpg"
    assert recovered.sbs_stats == player.sbs_stats


def test_unknown_country_persists_code_and_warns_once_per_run(metadata_reports, caplog):
    fixture = metadata_reports
    fixture.bio.update(birthCountryCode="ZZZ", nationalityCode="ZZZ")
    for _ in range(2):
        caplog.clear()
        player = publish(fixture)
        assert (player.birth_country, player.nation) == ("ZZZ", "ZZZ")
        assert (player.birth_country_abbr, player.nation_abbr) == ("ZZZ", "ZZZ")
        messages = [r.getMessage() for r in caplog.records]
        assert messages.count("Unknown country code from NHL API: ZZZ") == 1
        assert any("Unknown country codes from NHL API in upd_pls: ZZZ" in m for m in messages)


@pytest.mark.parametrize("birth_date,age", [("2000-03-02", 25), ("2000-03-01", 26)])
def test_biography_age_uses_birthday_boundary(metadata_reports, birth_date, age):
    metadata_reports.bio["birthDate"] = birth_date
    assert publish(metadata_reports).age == age
