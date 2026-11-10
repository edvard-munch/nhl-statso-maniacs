"""Owned comparison packets, independent quotas, explicit mutations and real races."""

import json

from django.db import transaction
from django.test import Client
from django.urls import reverse
import pytest

from players.models import Skater, Goalie
from players.tests.integration.tests_favorites_api_db import (
    saved,
    csrf,
    concurrent_changes,  # noqa: F401 -- shared season fixtures and race harness
)
from players.tests.integration.tests_players_season_table import table_players, stored_rows  # noqa: F401
from players.tests.integration.tests_saved_player_actions_db import actions, state  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def compared(saved):
    saved.owner.comparable_skaters.add(*[saved.players[name] for name in ("low", "old", "zero")])
    saved.owner.comparable_goalies.add(saved.goalie)
    saved.other.comparable_skaters.add(saved.players["high"])
    return saved


def listing(client, **params):
    return client.get(reverse("api_v1:comparison"), params)


def member_url(player_type="skater", nhl_id=1):
    return reverse(
        "api_v1:comparison-membership", kwargs={"player_type": player_type, "nhl_id": nhl_id}
    )


def group_url(player_type="skater"):
    return reverse("api_v1:comparison-group", kwargs={"player_type": player_type})


def write(client, method="put", player_type="skater", nhl_id=1, **kwargs):
    return getattr(client, method)(member_url(player_type, nhl_id), b"", content_type="", **kwargs)


def clear(client, player_type="skater", **kwargs):
    return client.delete(group_url(player_type), b"", content_type="", **kwargs)


def test_list_keeps_missing_zero_and_typed_players_with_unfiltered_quotas(client, compared):
    response = listing(client)
    assert response.status_code == 200
    data = response.json()
    rows = {row["nhl_id"]: row for row in data["results"]}
    assert data["count"] == 3 and rows.keys() == {1, 3, 4}
    assert rows[1]["stats"]["goals"] == 2
    assert rows[3]["stats"] is None and rows[3]["availability"] == "missing"
    assert rows[4]["stats"]["games"] == 0
    assert data["meta"]["scope"] == "season" and data["meta"]["season_id"] == "20262027"
    assert data["meta"]["quota"] == {
        "limit_per_type": 5,
        "skaters": {"count": 3, "remaining": 2, "over_limit": False},
        "goalies": {"count": 1, "remaining": 4, "over_limit": False},
    }
    goalie = listing(client, player_type="goalie").json()
    assert goalie["count"] == 1 and goalie["results"][0]["nhl_id"] == 1
    assert goalie["results"][0]["stats"]["wins"] == 2
    assert goalie["meta"]["quota"] == data["meta"]["quota"]
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
    assert "cookie" in response["Vary"].lower() and response["X-Request-ID"]
    assert "_player" not in str(data) and "favorite-api-other" not in str(data)


def test_queries_filter_order_and_paginate_season_values_without_hiding_saved_identity(
    client, compared
):
    data = listing(client, mode="averages", ordering="nhl_id", page_size=1).json()
    assert data["count"] == 3 and data["results"][0]["stats"]["goals"] == 0.2
    assert client.get(data["next"]).json()["results"][0]["nhl_id"] == 3
    filtered = listing(client, goals_min="3").json()
    assert filtered["count"] == 1 and filtered["meta"]["quota"]["skaters"]["count"] == 3
    for order in ("points", "-points"):
        assert listing(client, ordering=order).json()["results"][-1]["nhl_id"] == 3
    assert listing(client, goals_isnull="true").json()["count"] == 1
    assert listing(client, search="Historical").json()["count"] == 1
    assert listing(client, season_id="20302031").json()["count"] == 3
    Skater.objects.filter(nhl_id=1).update(sbs_stats=[None])
    invalid = next(row for row in listing(client).json()["results"] if row["nhl_id"] == 1)
    assert invalid["stats"] is None and invalid["availability"] == "unverified"
    assert invalid["teams"] == []
    Skater.objects.update(sbs_stats=[])
    Goalie.objects.update(sbs_stats=[])
    data = listing(client).json()
    assert data["count"] == 3 and data["meta"]["season_id"] is None


def test_career_packets_stay_separate_from_season_and_snapshot_and_support_averages(
    client, compared
):
    low = compared.players["low"]
    Skater.objects.filter(pk=low.pk).update(
        career_stats={"gamesPlayed": 10, "goals": 8, "avgToi": "12:34"},
        career_stats_avg={"gamesPlayed": 10, "goals": 0.8, "avgToi": "12:34"},
        goals=999,
    )
    totals = listing(client, scope="career", goals_min=5).json()
    assert totals["count"] == 1 and totals["results"][0]["stats"]["goals"] == 8
    assert totals["meta"]["scope"] == "career" and totals["meta"]["season_id"] is None
    assert totals["results"][0]["teams"] == []
    assert totals["results"][0]["availability"] == "partial"
    averages = listing(client, scope="career", mode="averages", search=low.name).json()
    stats = averages["results"][0]["stats"]
    assert stats["goals"] == 0.8 and stats["games"] == 10 and stats["avg_toi_seconds"] == 754
    assert listing(client, search=low.name).json()["results"][0]["stats"]["goals"] == 2
    Goalie.objects.filter(pk=compared.goalie.pk).update(career_stats={"gamesPlayed": 12, "wins": 7})
    goalies = listing(client, scope="career", player_type="goalie").json()
    assert goalies["results"][0]["stats"]["wins"] == 7
    assert goalies["results"][0]["stats"]["kind"] == "goalie_totals"
    Skater.objects.update(career_stats={})
    assert all(row["stats"] is None for row in listing(client, scope="career").json()["results"])


@pytest.mark.parametrize(
    "params",
    [
        {"scope": "career", "season_id": "20262027"},
        {"scope": "career", "team": "BUF"},
        {"scope": ""},
        {"scope": "all"},
        {"scope": ["season", "career"]},
        {"player_type": "goalie", "mode": "averages"},
        {"owner": "1"},
        {"ordering": "career_stats__goals"},
        {"season_id": "2026"},
        {"player_type": "goalie", "goals_min": "1"},
    ],
)
def test_invalid_queries_are_400_and_do_not_change_state(client, actions, params):
    before = state([actions.owner, actions.other])
    assert listing(client, **params).status_code == 400
    assert state([actions.owner, actions.other]) == before


def test_owned_read_is_bounded_and_does_not_write_or_call_network(
    client, compared, django_assert_num_queries, offline
):
    before = state([compared.owner, compared.other])
    snapshots = list(Skater.objects.order_by("pk").values())
    with django_assert_num_queries(9):
        assert listing(client, season_id="20262027").status_code == 200
    with django_assert_num_queries(8):
        assert listing(client, scope="career").status_code == 200
    assert snapshots == list(Skater.objects.order_by("pk").values())
    assert state([compared.owner, compared.other]) == before and not offline.called
    client.force_login(compared.other)
    assert [row["nhl_id"] for row in listing(client).json()["results"]] == [2]


@pytest.mark.parametrize("kind,player_type", [("skaters", "skater"), ("goalies", "goalie")])
def test_idempotent_mutations_preserve_favorites_other_accounts_and_opposite_type(
    client, actions, kind, player_type
):
    player = actions.create(kind)[0]
    player.favoriting.add(actions.owner, actions.other)
    player.comparing.add(actions.other)
    first = write(client, player_type=player_type, nhl_id=player.nhl_id)
    assert first.status_code == 201 and first.json()["is_compared"]
    assert write(client, player_type=player_type, nhl_id=player.nhl_id).status_code == 200
    assert player.comparing.count() == 2
    for _ in range(2):
        response = write(client, "delete", player_type, player.nhl_id)
        assert response.status_code == 204 and response.content == b""
    assert player.comparing.filter(pk=actions.other.pk).exists() and player.favoriting.count() == 2


def test_same_nhl_id_is_typed_and_reset_is_scoped_idempotent(client, compared):
    other_before = state([compared.other])
    favorites = (compared.owner.favorite_skaters.count(), compared.owner.favorite_goalies.count())
    assert write(client, "delete", "skater", 1).status_code == 204
    assert compared.owner.comparable_goalies.filter(nhl_id=1).exists()
    for _ in range(2):
        assert clear(client).status_code == 204
    assert compared.owner.comparable_skaters.count() == 0
    assert compared.owner.comparable_goalies.count() == 1
    assert favorites == (
        compared.owner.favorite_skaters.count(),
        compared.owner.favorite_goalies.count(),
    )
    assert state([compared.other]) == other_before
    assert clear(client, "goalie").status_code == 204
    assert listing(client, player_type="goalie").json()["count"] == 0


@pytest.mark.parametrize("kind,player_type", [("skaters", "skater"), ("goalies", "goalie")])
def test_independent_limits_and_over_limit_preservation(
    client, actions, kind, player_type, django_assert_num_queries
):
    opposite = "goalies" if kind == "skaters" else "skaters"
    getattr(actions.owner, "comparable_" + opposite).add(*actions.create(opposite, 5))
    players = actions.create(kind, 6)
    for player in players[:5]:
        assert write(client, player_type=player_type, nhl_id=player.nhl_id).status_code == 201
    blocked = write(client, player_type=player_type, nhl_id=players[5].nhl_id)
    assert (
        blocked.status_code == 409
        and blocked.json()["error"]["code"] == "comparison_quota_exceeded"
    )
    assert write(client, player_type=player_type, nhl_id=players[0].nhl_id).status_code == 200
    getattr(actions.owner, "comparable_" + kind).add(players[5])
    with django_assert_num_queries(9):
        data = listing(client, player_type=player_type, season_id="20262027").json()
    assert data["count"] == 6
    assert data["meta"]["quota"][kind] == {"count": 6, "remaining": 0, "over_limit": True}
    assert write(client, player_type=player_type, nhl_id=players[0].nhl_id).status_code == 200
    assert clear(client, player_type).status_code == 204
    assert getattr(actions.owner, "comparable_" + opposite).count() == 5
    assert write(client, player_type=player_type, nhl_id=players[0].nhl_id).status_code == 201


@pytest.mark.parametrize("target", ["member", "group", "list"])
def test_anonymous_requests_fail_closed(client, actions, target):
    player = actions.create("skaters")[0]
    player.comparing.add(actions.owner)
    before = state([actions.owner, actions.other])
    client.logout()
    response = (
        write(client, nhl_id=player.nhl_id)
        if target == "member"
        else clear(client)
        if target == "group"
        else listing(client)
    )
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "authentication_required"
    )
    assert state([actions.owner, actions.other]) == before


@pytest.mark.parametrize("mode", ["cookie", "http_only", "session"])
def test_mutations_and_reset_require_csrf_with_alternate_storage(actions, settings, mode):
    settings.CSRF_COOKIE_HTTPONLY = mode == "http_only"
    settings.CSRF_USE_SESSIONS = mode == "session"
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(actions.owner)
    player = actions.create("skaters")[0]
    assert write(strict, nhl_id=player.nhl_id).status_code == 403
    token = csrf(strict)
    assert write(strict, nhl_id=player.nhl_id, HTTP_X_CSRFTOKEN=token).status_code == 201
    for target in [member_url(nhl_id=player.nhl_id), group_url()]:
        assert strict.delete(target).status_code == 403
        assert (
            strict.delete(
                target, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://untrusted.invalid"
            ).status_code
            == 403
        )
    assert clear(strict, HTTP_X_CSRFTOKEN=token).status_code == 204
    assert write(strict, nhl_id=player.nhl_id, HTTP_X_CSRFTOKEN=token).status_code == 201
    assert write(strict, "delete", nhl_id=player.nhl_id, HTTP_X_CSRFTOKEN=token).status_code == 204


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("player_type,nhl_id", [("invalid", 1), ("skater", 0), ("goalie", 2**31)])
def test_invalid_target_is_404(client, actions, method, player_type, nhl_id):
    assert write(client, method, player_type, nhl_id).status_code == 404


def test_unknown_player_and_empty_reset_contract(client, actions):
    assert write(client, nhl_id=999999).status_code == 404
    assert write(client, "delete", nhl_id=999999).status_code == 204
    assert clear(client).status_code == 204
    assert clear(client, "invalid").status_code == 404
    assert listing(client).json()["results"] == []
    assert client.head(reverse("api_v1:comparison")).status_code == 200


@pytest.mark.parametrize("target", ["member", "group"])
@pytest.mark.parametrize("body", [{"user_id": 1}, {"is_compared": False}, [], None])
def test_mutations_reject_nonempty_or_nonobject_body(client, actions, target, body):
    player = actions.create("skaters")[0]
    player.comparing.add(actions.owner)
    url = member_url(nhl_id=player.nhl_id) if target == "member" else group_url()
    before = state([actions.owner])
    response = client.delete(url, json.dumps(body), content_type="application/json")
    assert response.status_code == 400 and state([actions.owner]) == before


def test_mutation_queries_methods_and_empty_json_are_explicit(client, actions):
    player = actions.create("skaters")[0]
    for url in [member_url(nhl_id=player.nhl_id), group_url()]:
        assert client.delete(url + "?owner=1").status_code == 400
        assert client.get(url).status_code == 405
        assert client.post(url).status_code == 405
    assert (
        client.put(
            member_url(nhl_id=player.nhl_id), "{}", content_type="application/json"
        ).status_code
        == 201
    )
    assert client.delete(group_url(), "{}", content_type="application/json").status_code == 204


def test_failed_serialization_and_reset_roll_back_membership(client, actions, monkeypatch):
    player = actions.create("skaters")[0]
    client.raise_request_exception = False

    def fail(*args):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(
        "players.api.comparison_serializers.ComparisonMembershipSerializer.to_representation", fail
    )
    assert write(client, nhl_id=player.nhl_id).status_code == 500
    assert not player.comparing.filter(pk=actions.owner.pk).exists()
    player.comparing.add(actions.owner)

    def failed_reset(owner, player_type):
        owner.comparable_skaters.clear()
        raise RuntimeError("synthetic clear failure")

    monkeypatch.setattr("players.api.comparison_views.clear_memberships", failed_reset)
    assert clear(client).status_code == 500
    assert player.comparing.filter(pk=actions.owner.pk).exists()


def test_schema_is_private_typed_nullable_and_documents_idempotent_statuses(
    client, django_assert_num_queries
):
    with django_assert_num_queries(0):
        schema = client.get(reverse("api_v1:schema")).json()
    paths = schema["paths"]
    assert paths["/api/v1/me/comparison/"]["get"]["security"] == [{"cookieAuth": []}]
    member = paths["/api/v1/me/comparison/{player_type}/{nhl_id}/"]
    assert {"200", "201", "403", "409"} <= member["put"]["responses"].keys()
    for route in [
        "/api/v1/me/comparison/{player_type}/",
        "/api/v1/me/comparison/{player_type}/{nhl_id}/",
    ]:
        operation = paths[route]["delete"]
        assert operation["security"] == [{"cookieAuth": []}]
        assert "content" not in operation["responses"]["204"]
    stats = schema["components"]["schemas"]["ComparisonPlayer"]["properties"]["stats"]
    assert stats["nullable"] and "#/components/schemas/ProfileStatistics" in json.dumps(stats)


@pytest.mark.django_db(transaction=True)
class TestComparisonConcurrency:
    @staticmethod
    def clients(owner, other=None):
        clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
        clients[0].force_login(owner)
        clients[1].force_login(other or owner)
        return clients, [csrf(client) for client in clients]

    @pytest.mark.parametrize("kind,player_type", [("skaters", "skater"), ("goalies", "goalie")])
    def test_final_typed_slot_is_not_overfilled(self, actions, kind, player_type):
        getattr(actions.owner, "comparable_" + kind).add(*actions.create(kind, 4))
        players = actions.create(kind, 2)
        clients, tokens = self.clients(actions.owner)
        a, b = concurrent_changes(
            clients[0],
            ("put", member_url(player_type, players[0].nhl_id), tokens[0]),
            clients[1],
            ("put", member_url(player_type, players[1].nhl_id), tokens[1]),
        )
        assert (a[0], b[0]) == (201, 409)
        assert b[1]["error"]["code"] == "comparison_quota_exceeded"
        assert getattr(actions.owner, "comparable_" + kind).count() == 5

    def test_different_types_can_each_fill_their_final_slot(self, actions):
        actions.owner.comparable_skaters.add(*actions.create("skaters", 4))
        actions.owner.comparable_goalies.add(*actions.create("goalies", 4))
        skater, goalie = actions.create("skaters")[0], actions.create("goalies")[0]
        clients, tokens = self.clients(actions.owner)
        a, b = concurrent_changes(
            clients[0],
            ("put", member_url("skater", skater.nhl_id), tokens[0]),
            clients[1],
            ("put", member_url("goalie", goalie.nhl_id), tokens[1]),
        )
        assert (a[0], b[0]) == (201, 201)
        assert (
            actions.owner.comparable_skaters.count()
            == actions.owner.comparable_goalies.count()
            == 5
        )

    @pytest.mark.parametrize("first_legacy", [True, False])
    def test_legacy_and_api_share_quota_lock(self, actions, first_legacy):
        actions.owner.comparable_skaters.add(*actions.create("skaters", 4))
        players = actions.create("skaters", 2)
        clients, tokens = self.clients(actions.owner)

        def request(index, legacy):
            player = players[index]
            return (
                "post" if legacy else "put",
                reverse("player_compare", args=[player.slug, player.nhl_id])
                if legacy
                else member_url(nhl_id=player.nhl_id),
                tokens[index],
            )

        a, b = concurrent_changes(
            clients[0], request(0, first_legacy), clients[1], request(1, not first_legacy)
        )
        assert a[0] == (200 if first_legacy else 201)
        assert b[0] == (409 if first_legacy else 200)
        if not first_legacy:
            assert b[1]["comp_quota_reached"] == 1
        assert actions.owner.comparable_skaters.count() == 5

    @pytest.mark.parametrize(
        "first_method,second_method",
        [("put", "put"), ("put", "delete"), ("delete", "put"), ("delete", "delete")],
    )
    def test_repeated_explicit_membership_follows_lock_order(
        self, actions, first_method, second_method
    ):
        player = actions.create("skaters")[0]
        if first_method == "delete":
            actions.owner.comparable_skaters.add(player)
        clients, tokens = self.clients(actions.owner)
        a, b = concurrent_changes(
            clients[0],
            (first_method, member_url(nhl_id=player.nhl_id), tokens[0]),
            clients[1],
            (second_method, member_url(nhl_id=player.nhl_id), tokens[1]),
        )
        assert a[0] in (201, 204) and b[0] in (200, 201, 204)
        assert player.comparing.filter(pk=actions.owner.pk).exists() == (second_method == "put")

    @pytest.mark.parametrize(
        "clear_first,legacy_reset", [(True, False), (False, False), (True, True), (False, True)]
    )
    def test_api_and_legacy_resets_serialize_with_additions(
        self, actions, clear_first, legacy_reset
    ):
        actions.owner.comparable_skaters.add(*actions.create("skaters", 4))
        player = actions.create("skaters")[0]
        clients, tokens = self.clients(actions.owner)
        reset_url = reverse("reset_comparison", args=["skaters"]) if legacy_reset else group_url()
        reset_method = "post" if legacy_reset else "delete"
        specs = [(reset_method, reset_url), ("put", member_url(nhl_id=player.nhl_id))]
        if not clear_first:
            specs.reverse()
        a, b = concurrent_changes(
            clients[0], (*specs[0], tokens[0]), clients[1], (*specs[1], tokens[1])
        )
        assert a[0] in (200, 201, 204) and b[0] in (200, 201, 204)
        assert actions.owner.comparable_skaters.count() == (1 if clear_first else 0)

    def test_different_accounts_do_not_wait_for_each_other(self, actions):
        player = actions.create("skaters")[0]
        clients, tokens = self.clients(actions.owner, actions.other)
        a, b = concurrent_changes(
            clients[0],
            ("put", member_url(nhl_id=player.nhl_id), tokens[0]),
            clients[1],
            ("put", member_url(nhl_id=player.nhl_id), tokens[1]),
            same_user=False,
        )
        assert (a[0], b[0]) == (201, 201) and player.comparing.count() == 2
