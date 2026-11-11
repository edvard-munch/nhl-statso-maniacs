"""Typed saved-game details, identity verification, nulls, units and read isolation."""

from copy import deepcopy
from datetime import timedelta
from io import StringIO
import json

from django.core.management import call_command
from django.db import connection
from django.urls import reverse
import pytest

from players.api import game_detail as reader
from players.models import Game, Gameday, Goalie, LoaderRun, LoaderScheduleState, Side, Skater
from players.tests.integration.tests_game_pages_db import game_page  # noqa: F401
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


def url(game):
    return reverse("api_v1:game-detail", args=[game.nhl_id])


def player(data, side="away", group="forwards"):
    return data["rosters"][side][group][0]


def change(fixture, key, function):
    value = fixture.players[key]
    value.refresh_from_db()
    function(value.gamelog_stats[fixture.day["date"]])
    value.save(update_fields=["gamelog_stats"])


def snapshot():
    models = (Game, Gameday, Skater, Goalie, Side, LoaderRun, LoaderScheduleState)
    return {model: list(model.objects.order_by("pk").values()) for model in models}


def test_saved_game_data_uses_actual_rosters_game_rows_and_numeric_units(client, game_page):
    f = game_page
    response = client.get(url(f.game))
    assert response.status_code == 200 and response["Content-Type"] == "application/json"
    data = response.json()
    assert (data["away_score"], data["home_score"]) == (1, 0)
    assert data["score_source"] == "legacy_result" and data["is_final"] == f.game.game_finished
    assert data["away_team"]["nhl_id"] == f.away.nhl_id
    for side, group, key, goals, pp, sh in [
        ("away", "forwards", "away_forward", 1, 61, 121),
        ("away", "defencemen", "away_defense", 2, 62, 122),
        ("home", "forwards", "home_forward", 3, 63, 123),
        ("home", "defencemen", "home_defense", 4, 64, 124),
    ]:
        row = player(data, side, group)
        assert row["nhl_id"] == f.players[key].nhl_id and row["player_type"] == "skater"
        assert row["stats"]["goals"] == goals
        assert row["stats"]["toi_seconds"] == 754
        assert (row["stats"]["pp_toi_seconds"], row["stats"]["sh_toi_seconds"]) == (pp, sh)
    goalie = player(data, group="goalies")
    assert goalie["player_type"] == "goalie" and goalie["stats"] == {
        "decision": "W",
        "toi_seconds": 3600,
        "goals_against": 2,
        "saves": 24,
        "shots_against": 26,
        "save_percentage": 0.923,
        "shutouts": 1,
    }
    assert len(data["rosters"]["away"]["goalies"]) == len(data["rosters"]["home"]["goalies"]) == 1
    assert f.players["away_bench"].nhl_id not in [
        row["nhl_id"] for row in data["rosters"]["away"]["goalies"]
    ]
    # Restrict sentinel checks to statistics: timestamps can legitimately contain
    # "09:59" or the digits "999", making whole-response substring checks flaky.
    for roster in data["rosters"].values():
        for group in roster.values():
            for entry in group:
                assert 999 not in entry["stats"].values()
                assert 9999 not in entry["stats"].values()
                for field in ("toi_seconds", "pp_toi_seconds", "sh_toi_seconds"):
                    assert entry["stats"].get(field) != 599
    assert "no-store" in response["Cache-Control"]


def test_known_zero_and_negative_plus_minus_are_preserved(client, game_page):
    def fill(row):
        row.update(
            goals=0,
            plusMinus=-2,
            pim=0,
            sog=0,
            hits=0,
            blockedShots=0,
            faceoffs=0,
            powerPlayPoints=0,
            shPoints=0,
            toi="00:00",
            powerPlayToi="00:00",
            shorthandedToi="00:00",
        )

    change(game_page, "away_forward", fill)
    row = player(client.get(url(game_page.game)).json())
    assert row["availability"] == "complete"
    assert row["stats"]["goals"] == 0 and row["stats"]["plus_minus"] == -2
    assert row["stats"]["toi_seconds"] == row["stats"]["pp_toi_seconds"] == 0


@pytest.mark.parametrize("value", [None, "", "00:60", -1, True, "unknown"])
def test_unknown_or_invalid_toi_is_null_not_zero(client, game_page, value):
    change(game_page, "away_forward", lambda row: row.update(powerPlayToi=value))
    data = client.get(url(game_page.game)).json()
    row = player(data)
    assert row["stats"]["pp_toi_seconds"] is None
    assert row["availability"] == "partial" and data["freshness"]["partial"]


@pytest.mark.parametrize("value", [None, "", "abc", True, -1, 1.5, "9" * 50])
def test_invalid_count_values_do_not_coerce_to_fabricated_integers(client, game_page, value):
    change(game_page, "away_forward", lambda row: row.update(goals=value))
    row = player(client.get(url(game_page.game)).json())
    assert row["stats"]["goals"] is None and row["availability"] == "partial"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-0.1", "92.3", True, {}, None])
def test_save_percentage_is_nullable_finite_fraction(client, game_page, value):
    change(game_page, "away_goalie", lambda row: row.update(savePctg=value))
    data = client.get(url(game_page.game)).json()
    row = player(data, group="goalies")
    assert row["stats"]["save_percentage"] is None
    assert row["availability"] == "partial"


@pytest.mark.parametrize("value", ["bad", "27/26", "24/26/3", "-1/26", None])
def test_invalid_save_pairs_are_unknown(client, game_page, value):
    change(game_page, "away_goalie", lambda row: row.update(saveShotsAgainst=value))
    row = player(client.get(url(game_page.game)).json(), group="goalies")
    assert row["stats"]["saves"] is row["stats"]["shots_against"] is None


def test_explicit_saved_goalie_counts_win_over_display_pair(client, game_page):
    change(game_page, "away_goalie", lambda row: row.update(saves=0, shotsAgainst=0, savePctg=0))
    row = player(client.get(url(game_page.game)).json(), group="goalies")
    assert (
        row["stats"]["saves"]
        == row["stats"]["shots_against"]
        == row["stats"]["save_percentage"]
        == 0
    )


@pytest.mark.parametrize(
    "damage", ["missing", "malformed", "wrong_game", "wrong_player", "wrong_type"]
)
def test_missing_or_mismatched_rows_keep_identity_but_not_unverified_stats(
    client, game_page, damage
):
    p = game_page.players["away_forward"]
    if damage == "missing":
        p.gamelog_stats.pop(game_page.day["date"])
    elif damage == "malformed":
        p.gamelog_stats[game_page.day["date"]] = ["not a row"]
    elif damage == "wrong_game":
        p.gamelog_stats[game_page.day["date"]]["gameId"] = 2026029999
    elif damage == "wrong_player":
        p.gamelog_stats[game_page.day["date"]]["player"]["nhl_id"] = 123
    else:
        p.gamelog_stats[game_page.day["date"]]["position"] = "G"
    p.save(update_fields=["gamelog_stats"])
    data = client.get(url(game_page.game)).json()
    row = player(data)
    assert row["nhl_id"] == p.nhl_id
    assert row["availability"] == (
        "missing" if damage in ("missing", "malformed") else "unverified"
    )
    assert all(value is None for value in row["stats"].values())
    assert row["sweater_number"] is row["game_position"] is None
    assert data["freshness"]["partial"]


def test_legacy_row_is_verified_by_ordered_teams_and_unique_same_date_appearance(client, game_page):
    change(game_page, "away_forward", lambda row: row.pop("gameId"))
    row = player(client.get(url(game_page.game)).json())
    assert row["stats"]["goals"] == 1 and row["availability"] != "unverified"
    other = Game.objects.create(nhl_id=2026020099, slug="same-date", gameday=game_page.game.gameday)
    other.home_forwards.add(game_page.players["away_forward"])
    row = player(client.get(url(game_page.game)).json())
    assert row["availability"] == "unverified" and row["stats"]["goals"] is None


def test_unstamped_wrong_side_metadata_does_not_qualify_as_game_specific(client, game_page):
    def wrong(row):
        row.pop("gameId")
        row["team"], row["opponent"] = row["opponent"], row["team"]

    change(game_page, "away_forward", wrong)
    assert player(client.get(url(game_page.game)).json())["availability"] == "unverified"


def test_duplicate_current_game_roster_membership_does_not_duplicate_verified_stats(
    client, game_page
):
    game_page.game.home_forwards.add(game_page.players["away_forward"])
    data = client.get(url(game_page.game)).json()
    assert player(data)["availability"] == "unverified"
    duplicate = next(
        row
        for row in data["rosters"]["home"]["forwards"]
        if row["nhl_id"] == game_page.players["away_forward"].nhl_id
    )
    assert duplicate["availability"] == "unverified"


def test_missing_groups_and_undated_games_are_explicitly_partial(client, game_page):
    game_page.game.away_goalies.clear()
    data = client.get(url(game_page.game)).json()
    assert data["rosters"]["away"]["goalies"] == [] and data["freshness"]["partial"]
    Game.objects.filter(pk=game_page.game.pk).update(gameday=None)
    data = client.get(url(game_page.game)).json()
    assert data["date"] is None
    assert player(data)["availability"] == "missing"
    assert data["freshness"]["partial"]


def test_player_identity_is_typed_even_when_skater_goalie_primary_keys_collide(client, game_page):
    skater = Skater.objects.create(
        id=99001, nhl_id=99001, name="Typed skater", birth_date="2000-01-01", games=0
    )
    goalie = Goalie.objects.create(
        id=99001, nhl_id=99002, name="Typed goalie", birth_date="2000-01-01", games=0
    )
    game_page.game.away_forwards.add(skater)
    game_page.game.away_goalies.add(goalie)
    data = client.get(url(game_page.game)).json()
    assert any(
        row["nhl_id"] == 99001 and row["player_type"] == "skater"
        for row in data["rosters"]["away"]["forwards"]
    )
    assert any(
        row["nhl_id"] == 99002 and row["player_type"] == "goalie"
        for row in data["rosters"]["away"]["goalies"]
    )


def test_current_profile_position_is_separate_from_game_position(client, game_page):
    p = game_page.players["away_forward"]
    p.position_abbr = "D"
    p.save(update_fields=["position_abbr"])
    row = player(client.get(url(game_page.game)).json())
    assert row["position_abbr"] == "D" and row["game_position"] == "C"


def test_sorted_rosters_are_deterministic(client, game_page):
    existing = game_page.players["away_forward"]
    existing.last_name = "Zulu"
    existing.save(update_fields=["last_name"])
    new = Skater.objects.create(
        nhl_id=99100, name="First", last_name="Alpha", birth_date="2000-01-01", games=0
    )
    game_page.game.away_forwards.add(new)
    assert [
        row["nhl_id"]
        for row in client.get(url(game_page.game)).json()["rosters"]["away"]["forwards"]
    ] == [new.nhl_id, existing.nhl_id]


def test_request_is_select_only_with_bounded_queries_no_templates_or_upstream(
    client, game_page, offline, monkeypatch, django_assert_num_queries
):
    before = snapshot()
    calls = offline.call_count

    def no_html(*args, **kwargs):
        raise AssertionError("JSON details must not render HTML")

    monkeypatch.setattr("players.game_refresh.render_to_string", no_html)

    def selects(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith("SELECT")
        assert "advisory" not in sql.lower() and "for update" not in sql.lower()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(selects), django_assert_num_queries(8):
        data = client.get(url(game_page.game)).json()
    assert data["nhl_id"] == game_page.game.nhl_id
    assert snapshot() == before and offline.call_count == calls


def test_legacy_identity_checks_are_batched_not_per_player(
    client, game_page, django_assert_num_queries
):
    for key in ("away_forward", "home_forward", "away_goalie", "home_goalie"):
        change(game_page, key, lambda row: row.pop("gameId"))
    with django_assert_num_queries(10):
        assert client.get(url(game_page.game)).status_code == 200


def test_public_data_has_no_private_history_or_viewer_state(client, game_page):
    public = client.get(url(game_page.game)).json()
    client.force_login(game_page.user)
    signed_in = client.get(url(game_page.game)).json()
    public["freshness"].pop("checked_at")
    signed_in["freshness"].pop("checked_at")
    public["freshness"].pop("age_seconds")
    signed_in["freshness"].pop("age_seconds")
    assert signed_in == public
    assert "favorites" not in json.dumps(public) and "career_stats" not in json.dumps(public)
    assert "gamelog_stats" not in json.dumps(public)
    assert "2026-11-20" not in json.dumps(public)


@pytest.mark.parametrize("identifier", [0, -1, 2147483648, 999999999999999999999, 123])
def test_missing_or_invalid_ids_are_json_404(client, identifier):
    response = client.get(f"/api/v1/games/{identifier}/")
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


def test_unknown_query_parameters_and_unsupported_methods_are_rejected(client, game_page):
    response = client.get(url(game_page.game) + "?date=2026-11-20")
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"
    response = client.post(url(game_page.game), {}, content_type="application/json")
    assert response.status_code == 405
    response = client.head(url(game_page.game))
    assert response.status_code == 200 and response.content == b""


def test_summary_and_freshness_rules_are_shared_with_scoreboard(client, game_page):
    day = game_page.day["date"]
    Game.objects.filter(pk=game_page.game.pk).update(
        updated_date=game_page.game.updated_date - timedelta(days=2)
    )
    detail = client.get(url(game_page.game)).json()
    summary = client.get(reverse("api_v1:games") + "?date=" + day).json()["results"][0]
    for key in (
        "nhl_id",
        "date",
        "away_team",
        "home_team",
        "away_score",
        "home_score",
        "is_final",
        "score_source",
        "state",
    ):
        assert detail[key] == summary[key]
    assert detail["freshness"]["is_final"] and not detail["freshness"]["is_stale"]
    assert detail["freshness"]["saved_at"] == summary["freshness"]["saved_at"]
    Game.objects.filter(pk=game_page.game.pk).update(game_finished=False)
    assert client.get(url(game_page.game)).json()["freshness"]["is_stale"]


def test_schema_has_typed_rosters_nullable_units_and_no_warnings(client):
    schema = client.get(reverse("api_v1:schema")).json()
    operation = schema["paths"]["/api/v1/games/{nhl_id}/"]["get"]
    assert operation["operationId"] == "game_retrieve"
    assert operation.get("security", []) in ([], [{}])
    fields = schema["components"]["schemas"]["SkaterGameStats"]["properties"]
    assert fields["pp_toi_seconds"]["nullable"] and fields["pp_toi_seconds"]["type"] == "integer"
    assert schema["components"]["schemas"]["GoalieGameStats"]["properties"]["save_percentage"][
        "nullable"
    ]
    output = StringIO()
    call_command(
        "spectacular", "--format", "openapi-json", "--validate", "--fail-on-warn", stdout=output
    )
