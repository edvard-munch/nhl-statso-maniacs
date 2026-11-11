"""Owned favorite membership and season data, including real quota races."""

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import Client
from django.urls import reverse
import pytest

from players.models import Goalie, Skater, Team
from players.tests.integration.tests_players_season_table import table_players, stored_rows  # noqa: F401
from players.tests.integration.tests_saved_player_actions_db import actions  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def saved(client, table_players, season_stats_data):
    owner = get_user_model().objects.create_user(username="favorite-api-owner")
    other = get_user_model().objects.create_user(username="favorite-api-other")
    owner.favorite_skaters.add(*[table_players[name] for name in ("low", "old", "zero")])
    other.favorite_skaters.add(table_players["high"])
    goalie = Goalie.objects.create(
        nhl_id=1,
        name="Typed Favorite Goalie",
        birth_date="2000-01-01",
        games=999,
        wins=999,
        position_abbr="G",
        sbs_stats=stored_rows(season_stats_data["cases"]["current_goalie"]),
    )
    owner.favorite_goalies.add(goalie)
    client.force_login(owner)
    return SimpleNamespace(owner=owner, other=other, players=table_players, goalie=goalie)


def listing(client, **params):
    return client.get(reverse("api_v1:favorites"), params)


def member_url(player_type="skater", nhl_id=1):
    return reverse(
        "api_v1:favorite-membership", kwargs={"player_type": player_type, "nhl_id": nhl_id}
    )


def csrf(client):
    return client.get(reverse("api_v1:auth-csrf")).json()["csrf_token"]


def write(client, method="put", player_type="skater", nhl_id=1, **kwargs):
    return getattr(client, method)(member_url(player_type, nhl_id), b"", content_type="", **kwargs)


def test_private_list_keeps_missing_and_zero_game_seasons_and_separates_typed_identity(
    client, saved
):
    data = listing(client).json()
    assert data["count"] == 3
    assert {row["nhl_id"] for row in data["results"]} == {1, 3, 4}
    rows = {row["nhl_id"]: row for row in data["results"]}
    assert rows[1]["stats"]["goals"] == 2
    assert rows[3]["stats"] is None and rows[3]["availability"] == "missing"
    assert rows[3]["teams"] == [] and rows[4]["stats"]["games"] == 0
    assert data["meta"]["season_id"] == "20262027"
    assert data["meta"]["quota"] == {
        "limit": 100,
        "skaters_count": 3,
        "goalies_count": 1,
        "total_count": 4,
        "remaining": 96,
        "over_limit": False,
    }
    goalie = listing(client, player_type="goalie").json()
    assert goalie["count"] == 1 and goalie["results"][0]["nhl_id"] == 1
    assert (
        goalie["results"][0]["player_type"] == "goalie"
        and goalie["results"][0]["stats"]["wins"] == 2
    )
    assert goalie["meta"]["quota"] == data["meta"]["quota"]
    assert "_player" not in str(data) and "favorite-api-other" not in str(data)


def test_averages_filters_ordering_and_pagination_operate_on_saved_season_values(client, saved):
    data = listing(client, mode="averages", ordering="nhl_id", page_size=1).json()
    assert data["count"] == 3 and data["results"][0]["stats"]["goals"] == 0.2
    second = client.get(data["next"]).json()
    assert second["results"][0]["nhl_id"] == 3 and second["meta"] == data["meta"]
    assert listing(client, page=4, page_size=1).status_code == 404
    filtered = listing(client, mode="averages", goals_min=0.1).json()
    assert filtered["count"] == 1 and filtered["results"][0]["nhl_id"] == 1
    assert filtered["meta"]["quota"]["total_count"] == 4
    nulls = listing(client, mode="averages", goals_isnull="true").json()
    assert {row["nhl_id"] for row in nulls["results"]} == {3, 4}
    for ordering in ("points", "-points"):
        assert listing(client, ordering=ordering).json()["results"][-1]["nhl_id"] == 3


def test_explicit_empty_season_retains_all_members_and_no_seasons_still_retains_identity(
    client, saved
):
    data = listing(client, season_id="20302031").json()
    assert data["count"] == 3 and data["meta"]["season_id"] == "20302031"
    assert all(row["stats"] is None for row in data["results"])
    Skater.objects.update(sbs_stats=[])
    Goalie.objects.update(sbs_stats=[])
    data = listing(client).json()
    assert data["count"] == 3 and data["meta"]["season_id"] is None


def test_unverified_season_is_retained_without_statistics_or_team_guesses(client, saved):
    Skater.objects.filter(nhl_id=1).update(sbs_stats=[None])
    row = next(row for row in listing(client).json()["results"] if row["nhl_id"] == 1)
    assert row["stats"] is None and row["availability"] == "unverified" and row["teams"] == []


def test_list_is_owned_private_and_data_read_only_with_bounded_queries(
    client, saved, django_assert_num_queries, offline
):
    models = (Skater, Goalie, Team)
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    with django_assert_num_queries(9):
        response = listing(client, season_id="20262027")
    assert response.status_code == 200
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
    assert "cookie" in response["Vary"].lower() and response["X-Request-ID"]
    assert before == {model: list(model.objects.order_by("pk").values()) for model in models}
    client.force_login(saved.other)
    assert [row["nhl_id"] for row in listing(client).json()["results"]] == [2]
    assert not offline.called


@pytest.mark.parametrize("method", ["put", "delete"])
def test_anonymous_mutations_require_authentication_and_do_not_change_memberships(
    client, actions, method
):
    client.logout()
    player = actions.create("skaters")[0]
    response = write(client, method, nhl_id=player.nhl_id)
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "authentication_required"
    )
    assert not player.favoriting.exists()
    assert listing(client).status_code == 403


def test_empty_list_and_head_do_not_create_membership(client, actions):
    data = listing(client).json()
    assert (
        data["count"] == 0 and data["results"] == [] and data["meta"]["quota"]["remaining"] == 100
    )
    response = client.head(reverse("api_v1:favorites"))
    assert response.status_code == 200 and response.content == b""


@pytest.mark.parametrize("kind,player_type", [("skaters", "skater"), ("goalies", "goalie")])
def test_put_and_delete_are_idempotent_and_preserve_other_account_and_comparison(
    client, actions, kind, player_type
):
    player = actions.create(kind)[0]
    player.favoriting.add(actions.other)
    player.comparing.add(actions.owner, actions.other)
    first = write(client, player_type=player_type, nhl_id=player.nhl_id)
    assert first.status_code == 201 and first.json()["is_favorite"]
    assert first.json()["quota"]["total_count"] == 1
    assert write(client, player_type=player_type, nhl_id=player.nhl_id).status_code == 200
    assert player.favoriting.filter(pk=actions.owner.pk).count() == 1
    for _ in range(2):
        response = write(client, "delete", player_type, player.nhl_id)
        assert response.status_code == 204 and response.content == b""
    assert player.favoriting.filter(pk=actions.other.pk).exists()
    assert (
        player.comparing.count() == 2 and not player.favoriting.filter(pk=actions.owner.pk).exists()
    )


def test_typed_memberships_do_not_conflate_same_nhl_id(client, saved):
    assert write(client, "delete", "skater", 1).status_code == 204
    assert saved.owner.favorite_goalies.filter(nhl_id=1).exists()
    assert not saved.owner.favorite_skaters.filter(nhl_id=1).exists()


def test_shared_quota_blocks_only_new_additions_and_allows_removal_and_retry(client, actions):
    actions.owner.favorite_skaters.add(*actions.create("skaters", 99))
    existing = actions.create("goalies")[0]
    assert write(client, player_type="goalie", nhl_id=existing.nhl_id).status_code == 201
    blocked = actions.create("skaters")[0]
    response = write(client, nhl_id=blocked.nhl_id)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "favorites_quota_exceeded"
    )
    assert write(client, player_type="goalie", nhl_id=existing.nhl_id).status_code == 200
    assert not blocked.favoriting.filter(pk=actions.owner.pk).exists()
    assert write(client, "delete", "goalie", existing.nhl_id).status_code == 204
    assert write(client, nhl_id=blocked.nhl_id).status_code == 201


def test_existing_over_limit_data_is_not_trimmed(client, actions, django_assert_num_queries):
    players = actions.create("skaters", 101)
    actions.owner.favorite_skaters.add(*players)
    with django_assert_num_queries(9):
        data = listing(client, season_id="20262027").json()
    assert data["count"] == 101 and len(data["results"]) == 50
    assert data["meta"]["quota"]["over_limit"] and data["meta"]["quota"]["remaining"] == 0
    assert len(listing(client, page_size=100).json()["results"]) == 100
    assert write(client, nhl_id=players[0].nhl_id).status_code == 200
    new = actions.create("goalies")[0]
    assert write(client, player_type="goalie", nhl_id=new.nhl_id).status_code == 409
    assert write(client, "delete", nhl_id=players[0].nhl_id).status_code == 204
    assert actions.owner.favorite_skaters.count() == 100


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
def test_missing_player_put_is_404_and_delete_is_absent_success(client, actions, kind):
    player_type = "skater" if kind == "skaters" else "goalie"
    assert write(client, player_type=player_type, nhl_id=999999).status_code == 404
    assert write(client, "delete", player_type, 999999).status_code == 204


@pytest.mark.parametrize(
    "player_type,nhl_id", [("invalid", 1), ("skater", 0), ("goalie", 2**31), ("skater", 10**30)]
)
@pytest.mark.parametrize("method", ["put", "delete"])
def test_invalid_target_is_json_404(client, actions, player_type, nhl_id, method):
    assert write(client, method, player_type, nhl_id).status_code == 404


@pytest.mark.parametrize("mode", ["cookie", "http_only", "session"])
def test_csrf_is_required_and_bootstrap_token_works_for_mutations(actions, settings, mode):
    settings.CSRF_COOKIE_HTTPONLY = mode == "http_only"
    settings.CSRF_USE_SESSIONS = mode == "session"
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(actions.owner)
    player = actions.create("skaters")[0]
    assert write(strict, nhl_id=player.nhl_id).status_code == 403
    token = csrf(strict)
    assert write(strict, nhl_id=player.nhl_id, HTTP_X_CSRFTOKEN=token).status_code == 201
    assert write(strict, "delete", nhl_id=player.nhl_id).status_code == 403
    assert player.favoriting.filter(pk=actions.owner.pk).exists()
    assert write(strict, "delete", nhl_id=player.nhl_id, HTTP_X_CSRFTOKEN=token).status_code == 204


@pytest.mark.parametrize("method", ["put", "delete"])
def test_cross_origin_mutation_is_rejected(actions, method):
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(actions.owner)
    player = actions.create("skaters")[0]
    response = write(
        strict,
        method,
        nhl_id=player.nhl_id,
        HTTP_X_CSRFTOKEN=csrf(strict),
        secure=True,
        HTTP_ORIGIN="https://foreign.invalid",
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"
    assert not player.favoriting.filter(pk=actions.owner.pk).exists()


@pytest.mark.parametrize(
    "params",
    [
        {"owner": 1},
        {"username": "other"},
        {"season_id": "2026-27"},
        {"player_type": "all"},
        {"player_type": "goalie", "mode": "averages"},
        {"ordering": "favoriting"},
        {"page_size": 101},
    ],
)
def test_list_invalid_filters_cannot_select_another_owner(client, actions, params):
    response = listing(client, **params)
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_parameters"


@pytest.mark.parametrize("body", [{"is_favorite": False}, {"user_id": 1}, [], None, False])
def test_mutation_body_is_empty_only(client, actions, body):
    player = actions.create("skaters")[0]
    response = client.put(
        member_url(nhl_id=player.nhl_id), json.dumps(body), content_type="application/json"
    )
    assert response.status_code == 400 and not player.favoriting.exists()


def test_mutation_query_and_methods_are_explicit(client, actions):
    player = actions.create("skaters")[0]
    assert (
        client.put(
            member_url(nhl_id=player.nhl_id) + "?owner=1", "{}", content_type="application/json"
        ).status_code
        == 400
    )
    assert client.get(member_url(nhl_id=player.nhl_id)).status_code == 405
    assert (
        client.post(
            member_url(nhl_id=player.nhl_id), "{}", content_type="application/json"
        ).status_code
        == 405
    )
    assert (
        client.post(reverse("api_v1:favorites"), "{}", content_type="application/json").status_code
        == 405
    )
    assert listing(client).status_code == 200


def test_serialization_failure_rolls_back_a_new_membership(client, actions, monkeypatch):
    player = actions.create("skaters")[0]

    def fail(self, instance):
        raise RuntimeError("synthetic response failure")

    monkeypatch.setattr(
        "players.api.favorite_serializers.FavoriteMembershipSerializer.to_representation", fail
    )
    client.raise_request_exception = False
    response = write(client, nhl_id=player.nhl_id)
    assert response.status_code == 500 and not player.favoriting.exists()


def test_schema_documents_private_reads_idempotent_statuses_and_nullable_stats(
    client, django_assert_num_queries
):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    listing = schema["paths"]["/api/v1/me/favorites/"]["get"]
    assert listing["security"] == [{"cookieAuth": []}]
    path = schema["paths"]["/api/v1/me/favorites/{player_type}/{nhl_id}/"]
    assert {"200", "201", "403", "409"} <= path["put"]["responses"].keys()
    assert (
        "204" in path["delete"]["responses"] and "content" not in path["delete"]["responses"]["204"]
    )
    stats = schema["components"]["schemas"]["FavoritePlayer"]["properties"]["stats"]
    assert stats["nullable"]
    assert "#/components/schemas/ProfileStatistics" in json.dumps(stats)


def concurrent_changes(
    first_client, first_request, second_client, second_request, *, same_user=True
):
    from time import monotonic, sleep

    locked, release, connected = Event(), Event(), Event()
    pids = {}

    def run(client, request, first):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[first] = cursor.fetchone()[0]
            if not first:
                connected.set()

            def hold(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if first and "FOR UPDATE" in sql:
                    locked.set()
                    assert release.wait(15)
                return result

            method, target, token = request
            with connection.execute_wrapper(hold):
                response = getattr(client, method)(
                    target, b"", content_type="", HTTP_X_CSRFTOKEN=token
                )
            return response.status_code, (
                response.json()
                if response.content
                and response.get("Content-Type", "").startswith("application/json")
                else None
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, first_client, first_request, True)
        try:
            assert locked.wait(10)
            second = pool.submit(run, second_client, second_request, False)
            assert connected.wait(10)
            if same_user:
                deadline = monotonic() + 10
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT %s = ANY(pg_blocking_pids(%s))", [pids[True], pids[False]]
                        )
                        blocked = cursor.fetchone()[0]
                    if blocked:
                        break
                    assert not second.done(), "Mutation bypassed the existing owner lock"
                    assert monotonic() < deadline
                    sleep(0.01)
            else:
                second.result(timeout=10)
        finally:
            release.set()
        return first.result(timeout=15), second.result(timeout=15)


@pytest.mark.django_db(transaction=True)
class TestFavoriteConcurrency:
    @staticmethod
    def clients(owner, other=None):
        clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
        clients[0].force_login(owner)
        clients[1].force_login(other or owner)
        return clients, [csrf(client) for client in clients]

    @pytest.mark.parametrize(
        "types", [("skater", "skater"), ("goalie", "goalie"), ("skater", "goalie")]
    )
    def test_final_shared_slot_cannot_be_overfilled(self, actions, types):
        actions.owner.favorite_skaters.add(*actions.create("skaters", 99))
        candidates = [
            actions.create("skaters" if kind == "skater" else "goalies")[0] for kind in types
        ]
        clients, tokens = self.clients(actions.owner)
        result = concurrent_changes(
            clients[0],
            ("put", member_url(types[0], candidates[0].nhl_id), tokens[0]),
            clients[1],
            ("put", member_url(types[1], candidates[1].nhl_id), tokens[1]),
        )
        assert result[0][0] == 201 and result[1][0] == 409
        assert result[1][1]["error"]["code"] == "favorites_quota_exceeded"
        assert (
            actions.owner.favorite_skaters.count() + actions.owner.favorite_goalies.count() == 100
        )
        assert not candidates[1].favoriting.filter(pk=actions.owner.pk).exists()

    @pytest.mark.parametrize("first_legacy", [True, False])
    def test_api_and_legacy_share_one_quota_lock(self, actions, first_legacy):
        actions.owner.favorite_skaters.add(*actions.create("skaters", 99))
        first, second = actions.create("skaters", 2)
        clients, tokens = self.clients(actions.owner)
        legacy = lambda player: reverse("player_favorite", args=[player.slug, player.nhl_id])
        requests = [
            (
                "post" if first_legacy else "put",
                legacy(first) if first_legacy else member_url(nhl_id=first.nhl_id),
                tokens[0],
            ),
            (
                "put" if first_legacy else "post",
                member_url(nhl_id=second.nhl_id) if first_legacy else legacy(second),
                tokens[1],
            ),
        ]
        a, b = concurrent_changes(clients[0], requests[0], clients[1], requests[1])
        assert a[0] == (200 if first_legacy else 201)
        assert b[0] == (409 if first_legacy else 200)
        if not first_legacy:
            assert b[1]["fav_quota_reached"] == 1
        assert actions.owner.favorite_skaters.count() == 100

    def test_simultaneous_repeated_put_is_not_a_toggle(self, actions):
        player = actions.create("skaters")[0]
        clients, tokens = self.clients(actions.owner)
        a, b = concurrent_changes(
            clients[0],
            ("put", member_url(nhl_id=player.nhl_id), tokens[0]),
            clients[1],
            ("put", member_url(nhl_id=player.nhl_id), tokens[1]),
        )
        assert (a[0], b[0]) == (201, 200)
        assert actions.owner.favorite_skaters.count() == 1

    @pytest.mark.parametrize(
        "first_method,second_method", [("put", "delete"), ("delete", "put"), ("delete", "delete")]
    )
    def test_explicit_states_follow_owner_lock_order(self, actions, first_method, second_method):
        player = actions.create("skaters")[0]
        if first_method == "delete":
            actions.owner.favorite_skaters.add(player)
        clients, tokens = self.clients(actions.owner)
        a, b = concurrent_changes(
            clients[0],
            (first_method, member_url(nhl_id=player.nhl_id), tokens[0]),
            clients[1],
            (second_method, member_url(nhl_id=player.nhl_id), tokens[1]),
        )
        assert a[0] in (201, 204) and b[0] in (201, 204)
        assert actions.owner.favorite_skaters.filter(pk=player.pk).exists() == (
            second_method == "put"
        )

    def test_other_accounts_do_not_wait_on_owner_lock(self, actions):
        first, second = actions.create("skaters", 2)
        clients, tokens = self.clients(actions.owner, actions.other)
        a, b = concurrent_changes(
            clients[0],
            ("put", member_url(nhl_id=first.nhl_id), tokens[0]),
            clients[1],
            ("put", member_url(nhl_id=second.nhl_id), tokens[1]),
            same_user=False,
        )
        assert a[0] == b[0] == 201
        assert actions.owner.favorite_skaters.count() == actions.other.favorite_skaters.count() == 1
