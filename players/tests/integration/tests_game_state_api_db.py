"""Public saved-state evidence never turns nonfinal/storage freshness into live."""

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
import pytest

from players.models import Game, ScheduledGame, Side
from players.tests.integration.tests_scoreboard_api_db import NOW, board  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


def get(client):
    response = client.get(reverse("api_v1:games"), {"date": "2026-11-09"})
    assert response.status_code == 200, response.content
    return response.json()["results"][0]


@pytest.mark.parametrize(
    "suffix,final,value,source,conflict",
    [
        ("0:0", False, "unknown", None, False),
        ("1:0", False, "unknown", None, False),
        ("", False, "unknown", None, False),
        ("1:0 (Live)", False, "live", "legacy_result", False),
        ("0:0 (Live)", False, "live", "legacy_result", False),
        ("1:0", True, "final", "legacy_final_flag", False),
        ("2:1 OT", False, "final", "legacy_result", False),
        ("2:1 SO", False, "final", "legacy_result", False),
        ("2:1 OT", True, "final", "legacy_final_flag", False),
        ("2:1 SO", True, "final", "legacy_final_flag", False),
        ("1:0 (Live)", True, "unknown", None, True),
        ("", True, "final", "legacy_final_flag", False),
    ],
)
def test_state_matrix_is_shared_by_scoreboard_and_details(
    client, board, suffix, final, value, source, conflict
):
    game = board[0](result="Fixture Away - Fixture Home " + suffix, final=final)
    summary = get(client)
    detail = client.get(reverse("api_v1:game-detail", args=[game.nhl_id])).json()
    assert (
        summary["state"]
        == detail["state"]
        == {
            "value": value,
            "source": source,
            "observed_at": None,
            "conflict": conflict,
        }
    )
    assert summary["is_final"] is detail["is_final"] is final
    if suffix in ("2:1 OT", "2:1 SO"):
        assert summary["score_outcome"] == suffix[-2:]


@pytest.mark.parametrize(
    "result",
    [
        "Fixture Away - Fixture Home 1:0 (LIVE)",
        "Fixture Away - Fixture Home 1:0 (Live) OT",
        "Fixture Away - Fixture Home 1:0 OT (Live)",
        "Fixture Away - Fixture Home 1:0 SO extra",
        "Fixture Away - Fixture Home 01:0 (Live)",
        "Fixture Home - Fixture Away 1:0 (Live)",
        "<b>Fixture Away - Fixture Home 1:0 (Live)</b>",
        "Fixture Away - Fixture Home tomorrow",
    ],
)
def test_unrecognized_results_do_not_supply_live_or_final_evidence(client, board, result):
    board[0](result=result)
    row = get(client)
    assert row["state"] == {
        "value": "unknown",
        "source": None,
        "observed_at": None,
        "conflict": False,
    }
    assert row["score_source"] is None and row["freshness"]["partial"]


@pytest.mark.parametrize("damage", ["missing", "duplicate", "same_team", "renamed"])
@pytest.mark.parametrize("suffix", ["1:0 (Live)", "2:1 OT"])
def test_result_state_requires_verified_side_and_team_identity(client, board, damage, suffix):
    game = board[0](result="Fixture Away - Fixture Home " + suffix)
    if damage == "missing":
        game.side_set.filter(side="home").delete()
    elif damage == "duplicate":
        Side.objects.create(nhl_side_id=999, game=game, side="away", team=board[3])
    elif damage == "same_team":
        game.side_set.filter(side="home").update(team=board[2])
    else:
        board[2].name = "Renamed away team"
        board[2].save()
    assert get(client)["state"]["value"] == "unknown"


def test_final_flag_is_separate_from_unverified_result_and_roster_completeness(client, board):
    game = board[0](result="unverified (Live)", final=True)
    game.side_set.all().delete()
    row = get(client)
    assert row["state"] == {
        "value": "final",
        "source": "legacy_final_flag",
        "observed_at": None,
        "conflict": False,
    }
    assert row["away_score"] is None and row["freshness"]["partial"]


@pytest.mark.parametrize("age_seconds", [0, 900, 901, 86400])
def test_storage_age_does_not_date_or_expire_legacy_live_evidence(client, board, age_seconds):
    game = board[0](result="Fixture Away - Fixture Home 1:0 (Live)")
    Game.objects.filter(pk=game.pk).update(updated_date=NOW - timedelta(seconds=age_seconds))
    row = get(client)
    assert row["state"] == {
        "value": "live",
        "source": "legacy_result",
        "observed_at": None,
        "conflict": False,
    }
    assert row["freshness"]["age_seconds"] == age_seconds
    assert row["freshness"]["is_stale"] is (age_seconds >= 900)
    first = row["state"]
    Game.objects.filter(pk=game.pk).update(updated_date=NOW + timedelta(days=1))
    assert get(client)["state"] == first


@pytest.mark.parametrize("schedule_state", ["FUT", "PRE", "LIVE", "FINAL", "OFF"])
def test_scheduler_discovery_is_not_a_game_state_observation(client, board, schedule_state):
    game = board[0]()
    ScheduledGame.objects.create(
        game_id=game.nhl_id,
        schedule_date="2026-11-09",
        starts_at=NOW,
        game_state=schedule_state,
        schedule_state="OK",
        discovered_at=NOW,
    )
    row = get(client)
    assert row["state"]["value"] == "unknown" and row["state"]["observed_at"] is None


def test_state_reads_are_bounded_and_leave_legacy_records_unchanged(client, board, offline):
    games = [board[0](result="Fixture Away - Fixture Home 1:0 (Live)") for _ in range(30)]
    before = list(Game.objects.order_by("pk").values())
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("api_v1:games"), {"date": "2026-11-09", "page_size": 1})
    assert response.status_code == 200
    assert len(queries) == 2
    assert all(query["sql"].lstrip().startswith("SELECT") for query in queries)
    assert response.json()["count"] == len(games)
    assert response.json()["results"][0]["state"]["value"] == "live"
    assert list(Game.objects.order_by("pk").values()) == before
    assert not offline.called


def test_schema_exposes_nullable_observation_and_shared_state_object(client):
    schema = client.get(reverse("api_v1:schema")).json()
    components = schema["components"]["schemas"]
    assert components["SavedGameStateValueEnum"]["enum"] == ["unknown", "live", "final"]
    assert components["SavedGameStateSourceEnum"]["enum"] == ["legacy_result", "legacy_final_flag"]
    assert components["SourceEnum"]["enum"] == ["none", "typed", "legacy", "ambiguous", "invalid"]
    fields = components["SavedGameState"]["properties"]
    assert set(fields) == {"value", "source", "observed_at", "conflict"}
    assert fields["source"]["nullable"] and fields["observed_at"]["nullable"]
    assert fields["observed_at"]["format"] == "date-time"
    for name in ("ScoreboardGame", "GameDetail", "GamelogGame"):
        assert components[name]["properties"]["state"]["$ref"].endswith("/SavedGameState")
