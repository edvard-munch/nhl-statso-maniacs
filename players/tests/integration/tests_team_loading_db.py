"""Synthetic NHL reports through real team saves and temporary logo storage."""

from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError, URLError
import re

import pytest
import requests
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError

from players.management.commands import upd_tms
from players.models import Game, Goalie, Side, Skater, Team


pytestmark = [pytest.mark.integration, pytest.mark.django_db]
LOGO = b'<svg xmlns="http://www.w3.org/2000/svg"><title>Synthetic team</title></svg>'


@pytest.fixture
def team_report():
    return [
        {
            "id": 9001,
            "name": {"default": "Fixture Team One", "fr": "Autre nom"},
            "abbrev": "FX1",
            "firstYearOfPlay": "2001",
        },
        {"id": 9002, "name": {"default": "Fixture Team Two"}, "abbrev": "FX2"},
    ]


@pytest.fixture
def logos(settings, tmp_path, requests_mock):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    state = {"calls": [], "errors": {}}

    def download(request, context):
        url = request.url
        assert url in {upd_tms.URL_TEAMS_LOGOS.format(abbr) for abbr in ("FX1", "FX2")}
        state["calls"].append(url)
        if url in state["errors"]:
            error = state["errors"][url]
            if isinstance(error, HTTPError):
                context.status_code = error.code
                return b"Missing logo"
            raise requests.ConnectionError(str(error))
        return LOGO

    requests_mock.get(re.compile(r"https://assets\.nhle\.com/"), content=download)
    return state


def test_team_command_creates_metadata_and_logos_and_replays_without_duplicates(
    team_report, logos, requests_mock
):
    requests_mock.get(upd_tms.URL_TEAMS, json={"teams": team_report})

    call_command("upd_tms")
    original_ids = dict(Team.objects.values_list("nhl_id", "pk"))
    call_command("upd_tms")

    assert dict(Team.objects.values_list("nhl_id", "pk")) == original_ids
    assert len(original_ids) == 2
    assert requests_mock.call_count == 4  # Two team reports and two logo downloads.
    assert logos["calls"] == [upd_tms.URL_TEAMS_LOGOS.format(abbr) for abbr in ("FX1", "FX2")]
    one = Team.objects.get(nhl_id=9001)
    two = Team.objects.get(nhl_id=9002)
    assert (one.name, one.abbr, one.slug, one.nhl_debut) == (
        "Fixture Team One",
        "FX1",
        "fixture-team-one",
        "2001",
    )
    assert (two.name, two.abbr, two.slug, two.nhl_debut) == (
        "Fixture Team Two",
        "FX2",
        "fixture-team-two",
        "",
    )
    for team in (one, two):
        assert team.image.name == "teams_logos/{}.svg".format(team.slug)
        assert Path(team.image.path).read_bytes() == LOGO


@pytest.mark.parametrize("include_debut", [False, True])
def test_team_refresh_preserves_identity_links_slug_and_unreported_metadata(
    team_report, logos, include_debut
):
    team = Team.objects.create(
        nhl_id=9001,
        name="Original Team",
        abbr="OLD",
        nhl_debut="1991",
        arena_name="Saved Arena",
        arena_location="Saved City",
        division="Saved Division",
        conference="Saved Conference",
        off_site="https://saved.example.invalid/",
    )
    team.image.save("original-team.svg", ContentFile(LOGO))
    original_pk, original_slug, original_image = team.pk, team.slug, team.image.name
    history = [{"season": "2025-26", "teamAbbr": "OLD", "gamesPlayed": 4}]
    players = [
        model.objects.create(
            nhl_id=900001,
            name="Fixture " + model.__name__,
            team=team,
            birth_date="2000-01-01",
            games=4,
            sbs_stats=history,
        )
        for model in (Skater, Goalie)
    ]
    game = Game.objects.create(nhl_id=9000001)
    side = Side.objects.create(team=team, game=game, nhl_side_id=90001, side="home")
    payload = deepcopy(team_report[0])
    if not include_debut:
        payload.pop("firstYearOfPlay")

    upd_tms.import_team(payload)
    upd_tms.import_team(payload)

    team.refresh_from_db()
    assert team.pk == original_pk
    assert Team.objects.count() == 1
    assert (team.name, team.abbr) == ("Fixture Team One", "FX1")
    assert (team.slug, team.image.name) == (original_slug, original_image)
    assert team.nhl_debut == ("2001" if include_debut else "1991")
    assert (
        team.arena_name,
        team.arena_location,
        team.division,
        team.conference,
        team.off_site,
    ) == (
        "Saved Arena",
        "Saved City",
        "Saved Division",
        "Saved Conference",
        "https://saved.example.invalid/",
    )
    for player in players:
        player.refresh_from_db()
        assert player.team_id == original_pk
        assert player.sbs_stats == history
    side.refresh_from_db()
    assert side.team_id == original_pk
    assert list(game.teams.values_list("pk", flat=True)) == [original_pk]
    assert Path(team.image.path).read_bytes() == LOGO
    assert not logos["calls"]


@pytest.mark.parametrize("stored_image", ["", "teams_logos/outdated-name.svg"])
def test_cached_logo_is_attached_without_downloading(team_report, logos, settings, stored_image):
    team = Team.objects.create(nhl_id=9001, name="Fixture Team One", image=stored_image)
    cached = Path(settings.MEDIA_ROOT) / "teams_logos/fixture-team-one.svg"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(LOGO)

    upd_tms.import_team(team_report[0])

    team.refresh_from_db()
    assert team.image.name == "teams_logos/fixture-team-one.svg"
    assert Path(team.image.path).read_bytes() == LOGO
    assert not logos["calls"]


def test_deleted_logo_is_downloaded_again_on_replay(team_report, logos):
    upd_tms.import_team(team_report[0])
    team = Team.objects.get(nhl_id=9001)
    original_pk, original_image = team.pk, team.image.name
    Path(team.image.path).unlink()

    upd_tms.import_team(team_report[0])

    team.refresh_from_db()
    assert (team.pk, team.image.name) == (original_pk, original_image)
    assert Path(team.image.path).read_bytes() == LOGO
    assert logos["calls"] == [upd_tms.URL_TEAMS_LOGOS.format("FX1")] * 2
    assert Team.objects.count() == 1


def test_team_report_connection_failure_leaves_existing_rows_untouched(logos, requests_mock):
    Team.objects.create(nhl_id=9001, name="Saved Team", abbr="SAV", nhl_debut="1991")
    before = list(Team.objects.values())
    requests_mock.get(
        upd_tms.URL_TEAMS, exc=requests.exceptions.ConnectionError("synthetic offline")
    )

    with pytest.raises(CommandError, match="CONNECTION COULD NOT BE ESTABLISHED"):
        call_command("upd_tms")

    assert list(Team.objects.values()) == before
    assert not logos["calls"]


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_optional_logo_failure_keeps_metadata_and_next_team_and_retries_on_replay(
    team_report, logos, requests_mock, failure
):
    url = upd_tms.URL_TEAMS_LOGOS.format("FX1")
    logos["errors"][url] = (
        HTTPError(url, 404, "synthetic missing logo", None, None)
        if failure == "http"
        else URLError("synthetic offline")
    )
    requests_mock.get(upd_tms.URL_TEAMS, json={"teams": team_report})
    call_command("upd_tms")
    original_ids = dict(Team.objects.values_list("nhl_id", "pk"))
    assert len(original_ids) == 2
    assert Team.objects.get(nhl_id=9001).image.name == ""
    assert Team.objects.get(nhl_id=9001).nhl_debut == "2001"
    assert Path(Team.objects.get(nhl_id=9002).image.path).read_bytes() == LOGO

    logos["errors"].clear()
    call_command("upd_tms")

    assert dict(Team.objects.values_list("nhl_id", "pk")) == original_ids
    for team in Team.objects.all():
        assert Path(team.image.path).read_bytes() == LOGO
    attempts = 3 if failure == "connection" else 1
    assert logos["calls"] == [url] * attempts + [upd_tms.URL_TEAMS_LOGOS.format("FX2"), url]
