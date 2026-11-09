"""Exact-date JSON scoreboard contracts over synthetic saved games only."""

from datetime import date, datetime, timedelta, timezone as utc
from itertools import count
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
import pytest

from players.api import scoreboard as reader
from players.models import Game, Gameday, Goalie, LoaderRun, LoaderScheduleState, Side, Skater, Team
from players.tests.integration.tests_upd_gms_rosters_db import loaded_game, load  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
NOW = datetime(2026, 11, 9, 20, tzinfo=utc.utc)


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(reader.timezone, "now", lambda: NOW)
    away = Team.objects.create(nhl_id=1, name="Fixture Away", abbr="NJD")
    home = Team.objects.create(nhl_id=7, name="Fixture Home", abbr="BUF")
    day = Gameday.objects.create(day="2026-11-09")
    identifiers = count(1)

    def create(*, result="Fixture Away - Fixture Home 0:2", final=False, day=day):
        index = next(identifiers)
        game = Game.objects.create(
            nhl_id=2026020000 + index,
            slug=f"fixture-game-{index}",
            gameday=day,
            result=result,
            game_finished=final,
        )
        Side.objects.create(nhl_side_id=index * 2, game=game, team=away, side="away")
        Side.objects.create(nhl_side_id=index * 2 + 1, game=game, team=home, side="home")
        return game

    return create, day, away, home


def get(client, query="date=2026-11-09"):
    return client.get(reverse("api_v1:games") + "?" + query)


def test_public_scoreboard_has_explicit_data_and_verified_zero_score(client, board):
    create, day, away, home = board
    game = create()
    response = get(client)
    assert response.status_code == 200 and response["Content-Type"] == "application/json"
    data = response.json()
    assert set(data) == {"count", "next", "previous", "results", "meta"}
    assert data["count"] == 1 and data["next"] is data["previous"] is None
    row = data["results"][0]
    assert row["nhl_id"] == game.nhl_id and row["date"] == "2026-11-09"
    assert row["slug"] == game.slug and row["is_final"] is False
    assert row["away_team"] == {
        "nhl_id": 1,
        "name": "Fixture Away",
        "abbr": "NJD",
        "slug": away.slug,
    }
    assert row["home_team"]["nhl_id"] == home.nhl_id
    assert (row["away_score"], row["home_score"]) == (0, 2)
    assert row["score_source"] == "legacy_result" and row["score_outcome"] is None
    assert row["freshness"]["partial"] is False
    assert "result" not in row and "html" not in row and "text" not in row["freshness"]
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize(
    "suffix,outcome", [("1:0", None), ("1:0 (Live)", None), ("2:1 OT", "OT"), ("2:1 SO", "SO")]
)
def test_known_loader_score_formats(client, board, suffix, outcome):
    board[0](result="Fixture Away - Fixture Home " + suffix)
    row = get(client).json()["results"][0]
    assert row["away_score"] >= 1 and row["home_score"] is not None
    assert row["score_outcome"] == outcome and not row["freshness"]["partial"]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "Fixture Away - Fixture Home ",
        "Fixture Home - Fixture Away 2:1",
        "Fixture Away - Fixture Home -1:0",
        "Fixture Away - Fixture Home 01:2",
        "Fixture Away - Fixture Home 2:1 unknown",
        "<b>Fixture Away - Fixture Home 2:1</b>",
    ],
)
def test_unknown_or_ambiguous_result_is_null_not_guessed(client, board, value):
    board[0](result=value)
    data = get(client).json()
    row = data["results"][0]
    assert row["away_score"] is row["home_score"] is row["score_source"] is None
    assert row["freshness"]["partial"] and data["meta"]["freshness"]["partial"]


@pytest.mark.parametrize("damage", ["missing", "duplicate", "same_team", "renamed"])
def test_team_identity_problems_do_not_invent_ordered_scores(client, board, damage):
    create, day, away, home = board
    game = create()
    if damage == "missing":
        game.side_set.filter(side="home").delete()
    elif damage == "duplicate":
        Side.objects.create(nhl_side_id=999, game=game, side="away", team=home)
    elif damage == "same_team":
        game.side_set.filter(side="home").update(team=away)
    else:
        away.name = "Renamed team"
        away.save()
    row = get(client).json()["results"][0]
    assert row["away_score"] is row["home_score"] is None
    assert row["freshness"]["partial"]
    if damage == "missing":
        assert row["home_team"] is None
    if damage == "duplicate":
        assert row["away_team"] is None


def test_exact_day_and_empty_date_never_fall_back_to_another_day(client, board):
    create, day, away, home = board
    create()
    later = Gameday.objects.create(day="2026-11-10")
    create(day=later)
    assert get(client).json()["count"] == 1
    data = get(client, "date=2000-01-01").json()
    assert data["count"] == 0 and data["results"] == []
    assert data["meta"]["date"] == "2000-01-01"
    fresh = data["meta"]["freshness"]
    assert not fresh["has_data"] and not fresh["is_stale"]
    assert fresh["saved_at"] is fresh["age_seconds"] is None


@pytest.mark.parametrize(
    "query,field",
    [
        ("", "date"),
        ("date=", "date"),
        ("date=2026-02-30", "date"),
        ("date=2026-2-03", "date"),
        ("date=20261109", "date"),
        ("date=2026-11-09T00:00:00Z", "date"),
        ("date=2026-11-09&date=2026-11-10", "date"),
        ("date=2026-11-09&other=x", "other"),
        ("date=2026-11-09&page=0", "page"),
        ("date=2026-11-09&page=1.0", "page"),
        ("date=2026-11-09&page_size=101", "page_size"),
        ("date=2026-11-09&page_size=-1", "page_size"),
        ("date=2026-11-09&page=1&page=2", "page"),
    ],
)
def test_invalid_queries_are_typed_400_before_any_database_query(
    client, query, field, django_assert_num_queries
):
    with django_assert_num_queries(0):
        response = get(client, query)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameters"
    assert field in response.json()["error"]["fields"]


def test_pagination_is_stable_and_preserves_requested_date(client, board):
    create = board[0]
    games = [create() for _ in range(3)]
    first = get(client, "date=2026-11-09&page_size=2").json()
    assert first["count"] == 3
    assert [row["nhl_id"] for row in first["results"]] == [item.nhl_id for item in games[:2]]
    assert parse_qs(urlparse(first["next"]).query) == {
        "date": ["2026-11-09"],
        "page_size": ["2"],
        "page": ["2"],
    }
    last = client.get(first["next"]).json()
    assert [row["nhl_id"] for row in last["results"]] == [games[-1].nhl_id]
    assert last["previous"] and last["next"] is None
    assert last["meta"] == first["meta"]
    response = get(client, "date=2026-11-09&page=99")
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


def test_full_date_metadata_does_not_depend_on_which_page_is_displayed(client, board):
    create = board[0]
    game = create()
    create(result="malformed legacy data")
    Game.objects.filter(pk=game.pk).update(updated_date=NOW - timedelta(minutes=20))
    data = get(client, "date=2026-11-09&page_size=1").json()
    assert len(data["results"]) == 1
    assert data["meta"]["freshness"]["partial"] and data["meta"]["freshness"]["is_stale"]


def test_staleness_uses_oldest_unfinished_save_and_does_not_age_final_games(client, board):
    create = board[0]
    live = create()
    final = create(final=True)
    Game.objects.filter(pk=live.pk).update(updated_date=NOW - timedelta(minutes=15))
    Game.objects.filter(pk=final.pk).update(updated_date=NOW - timedelta(days=5))
    data = get(client).json()
    first, second = data["results"]
    assert first["freshness"]["is_stale"] and not second["freshness"]["is_stale"]
    assert data["meta"]["freshness"]["saved_at"] == first["freshness"]["saved_at"]
    assert (
        first["freshness"]["checked_at"]
        == second["freshness"]["checked_at"]
        == data["meta"]["freshness"]["checked_at"]
    )
    assert first["freshness"]["checked_at"].endswith("+00:00") or first["freshness"][
        "checked_at"
    ].endswith("Z")
    Game.objects.filter(pk=live.pk).update(game_finished=True)
    again = get(client).json()["meta"]["freshness"]
    assert again["is_final"] and not again["is_stale"]
    assert again["saved_at"] == first["freshness"]["saved_at"]


def test_repeated_checks_do_not_claim_new_saved_data(client, board, monkeypatch):
    board[0]()
    first = get(client).json()["results"][0]["freshness"]
    monkeypatch.setattr(reader.timezone, "now", lambda: NOW + timedelta(minutes=1))
    second = get(client).json()["results"][0]["freshness"]
    assert second["saved_at"] == first["saved_at"] and second["checked_at"] != first["checked_at"]


def test_saved_loader_output_is_read_without_upstream_calls(client, loaded_game, offline):
    game = load(loaded_game)
    before = offline.call_count
    row = get(client, "date=" + loaded_game.day["date"]).json()["results"][0]
    assert (row["away_score"], row["home_score"]) == (1, 0)
    assert row["is_final"] == game.game_finished
    assert row["away_team"]["nhl_id"] == loaded_game.away.nhl_id
    assert offline.call_count == before


def test_queries_are_bounded_select_only_with_no_state_or_membership_writes(
    client, board, offline, django_assert_num_queries
):
    for _ in range(4):
        board[0]()
    models = (Game, Gameday, Team, Side, Skater, Goalie, LoaderRun, LoaderScheduleState)
    before = {model: list(model.objects.order_by("pk").values()) for model in models}

    def select_only(execute, sql, params, many, context):
        assert sql.lstrip().upper().startswith("SELECT")
        assert "advisory" not in sql.lower() and "for update" not in sql.lower()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(select_only), django_assert_num_queries(2):
        response = get(client)
    assert response.status_code == 200
    assert {model: list(model.objects.order_by("pk").values()) for model in models} == before
    assert not offline.called


def test_public_response_is_identical_for_signed_in_viewer_and_does_not_expose_private_fields(
    client, board
):
    board[0]()
    public = get(client).json()
    user = get_user_model().objects.create_user(username="private-scoreboard-viewer")
    client.force_login(user)
    signed_in = get(client).json()
    assert signed_in == public
    assert "favorites" not in str(signed_in) and "email" not in str(signed_in)


def test_read_methods_and_unsupported_methods(client, board):
    board[0]()
    url = reverse("api_v1:games") + "?date=2026-11-09"
    response = client.head(url)
    assert response.status_code == 200 and response.content == b""
    response = client.post(url, {}, content_type="application/json")
    assert response.status_code == 405 and response.json()["error"]["code"] == "method_not_allowed"
    assert client.get(url, HTTP_ACCEPT="text/html").status_code == 406


def test_scoreboard_schema_declares_required_date_pagination_and_public_access(client):
    schema = client.get(reverse("api_v1:schema")).json()
    operation = schema["paths"]["/api/v1/games/"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["date"]["required"] and parameters["date"]["schema"]["format"] == "date"
    assert parameters["page_size"]["schema"]["maximum"] == 100
    assert operation.get("security", []) in ([], [{}])
    assert (
        "200" in operation["responses"]
        and "400" in operation["responses"]
        and "404" in operation["responses"]
    )
    response = schema["components"]["schemas"]["ScoreboardResponse"]["properties"]
    assert set(response) == {"count", "next", "previous", "results", "meta"}


def test_default_page_size_is_bounded_and_api_does_not_render_templates(client, board, monkeypatch):
    create, day, away, home = board
    Game.objects.bulk_create(
        [
            Game(nhl_id=2026030000 + index, slug=f"bulk-game-{index}", gameday=day)
            for index in range(51)
        ]
    )

    def no_html(*args, **kwargs):
        raise AssertionError("JSON scoreboard must not render HTML")

    monkeypatch.setattr("players.game_refresh.render_to_string", no_html)
    data = get(client).json()
    assert data["count"] == 51 and len(data["results"]) == 50
    assert data["next"] and data["previous"] is None
