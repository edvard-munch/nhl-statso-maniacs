"""Saved-player mutation boundaries with real M2M persistence and actual quotas."""

from types import SimpleNamespace

from django.contrib.auth.models import User
from django.urls import reverse
import pytest

from players import utils
from players.models import Goalie, Skater


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def offline(requests_mock):
    return requests_mock


@pytest.fixture
def actions(client):
    owner = User.objects.create_user(username="actions-owner")
    other = User.objects.create_user(username="actions-other")
    client.force_login(owner)
    next_id = [9000000]

    def create(kind, count=1):
        model = Skater if kind == "skaters" else Goalie
        players = []
        for _ in range(count):
            next_id[0] += 1
            nhl_id = next_id[0]
            players.append(
                model(
                    nhl_id=nhl_id,
                    name=f"Saved Player {nhl_id}",
                    slug=f"saved-player-{nhl_id}",
                    birth_date="2000-01-01",
                    games=0,
                    position_abbr="C" if kind == "skaters" else "G",
                    sbs_stats=[],
                    career_stats={},
                )
            )
        return model.objects.bulk_create(players)

    return SimpleNamespace(owner=owner, other=other, create=create)


def state(users):
    return {
        user.pk: {
            relation: list(getattr(user, relation).order_by("pk").values_list("pk", flat=True))
            for relation in (
                "favorite_skaters",
                "favorite_goalies",
                "comparable_skaters",
                "comparable_goalies",
            )
        }
        for user in users
    }


def toggle(client, player, route, **params):
    return client.post(
        reverse(route, args=[player.slug, player.nhl_id]),
        params,
        query_params={"season": "20262027", **params},
    )


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
def test_favorites_share_actual_quota_and_allow_remove_then_add_at_capacity(client, actions, kind):
    owner, other = actions.owner, actions.other
    skaters = actions.create("skaters", utils.FAVORITES_QUOTA - 2)
    goalie = actions.create("goalies")[0]
    owner.favorite_skaters.add(*skaters)
    owner.favorite_goalies.add(goalie)
    candidate = actions.create(kind)[0]
    blocked = actions.create("goalies" if kind == "skaters" else "skaters")[0]
    blocked.favoriting.add(other)
    before_other = state([other])
    response = toggle(client, candidate, "player_favorite")
    assert response.status_code == 200
    assert "fav_quota_reached" not in response.json()
    assert owner.favorite_skaters.count() + owner.favorite_goalies.count() == 100
    before = state([owner, other])
    response = toggle(client, blocked, "player_favorite")
    assert response.json()["fav_quota_reached"] == 1
    assert state([owner, other]) == before
    response = toggle(client, candidate, "player_favorite")
    assert "fav_quota_reached" not in response.json()
    assert response.json()["skaters_count"] + response.json()["goalies_count"] == 99
    assert toggle(client, blocked, "player_favorite").status_code == 200
    assert blocked.favoriting.filter(pk=owner.pk).exists()
    assert owner.favorite_skaters.count() + owner.favorite_goalies.count() == 100
    assert state([other]) == before_other
    assert owner.comparable_skaters.count() == owner.comparable_goalies.count() == 0


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
def test_comparison_limits_are_independent_and_removal_works_when_full(client, actions, kind):
    owner, other = actions.owner, actions.other
    opposite = "goalies" if kind == "skaters" else "skaters"
    other_group = actions.create(opposite, utils.COMPARISON_QUOTA)
    getattr(owner, "comparable_" + opposite).add(*other_group)
    candidate = actions.create(kind)[0]
    candidate.favoriting.add(owner)
    response = toggle(client, candidate, "player_compare")
    assert response.status_code == 200
    assert "comp_quota_reached" not in response.json()
    getattr(owner, "comparable_" + kind).add(*actions.create(kind, utils.COMPARISON_QUOTA - 1))
    blocked = actions.create(kind)[0]
    blocked.comparing.add(other)
    before = state([owner, other])
    response = toggle(client, blocked, "player_compare")
    assert response.json()["comp_quota_reached"] == 1
    assert state([owner, other]) == before
    response = toggle(client, candidate, "player_compare")
    assert "comp_quota_reached" not in response.json()
    assert getattr(owner, "comparable_" + kind).count() == 4
    assert "comp_quota_reached" not in toggle(client, blocked, "player_compare").json()
    assert getattr(owner, "comparable_" + kind).count() == 5
    assert getattr(owner, "comparable_" + opposite).count() == 5
    assert candidate.favoriting.filter(pk=owner.pk).exists()
    assert blocked.comparing.filter(pk=other.pk).exists()


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
@pytest.mark.parametrize(
    "route,relation", [("player_favorite", "favoriting"), ("player_compare", "comparing")]
)
def test_repeated_toggle_never_duplicates_or_changes_other_users_and_player_data(
    client, actions, kind, route, relation
):
    player = actions.create(kind)[0]
    getattr(player, relation).add(actions.other)
    before_player = type(player).objects.values().get(pk=player.pk)
    for expected in (True, False, True, False):
        response = toggle(client, player, route, user=actions.other.pk, author=actions.other.pk)
        assert response.status_code == 200
        assert getattr(player, relation).filter(pk=actions.owner.pk).exists() is expected
        assert getattr(player, relation).filter(pk=actions.other.pk).exists()
        assert getattr(player, relation).count() == (2 if expected else 1)
        assert type(player).objects.values().get(pk=player.pk) == before_player


@pytest.mark.parametrize("route", ["player_favorite", "player_compare"])
@pytest.mark.parametrize("invalid", ["slug", "id"])
def test_missing_saved_action_target_returns_404_without_mutations(client, actions, route, invalid):
    player = actions.create("skaters")[0]
    player.favoriting.add(actions.owner, actions.other)
    player.comparing.add(actions.owner, actions.other)
    before = state([actions.owner, actions.other])
    response = client.post(
        reverse(
            route,
            args=[
                "wrong-slug" if invalid == "slug" else player.slug,
                99999999 if invalid == "id" else player.nhl_id,
            ],
        ),
        {"season": "20262027"},
    )
    assert response.status_code == 404
    assert state([actions.owner, actions.other]) == before


@pytest.mark.parametrize("route", ["player_favorite", "player_compare"])
def test_anonymous_post_does_not_mutate_existing_saved_memberships(client, actions, route):
    player = actions.create("goalies")[0]
    player.favoriting.add(actions.owner)
    player.comparing.add(actions.other)
    before = state([actions.owner, actions.other])
    client.logout()
    response = client.post(
        reverse(route, args=[player.slug, player.nhl_id]), {"user": actions.owner.pk}
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert state([actions.owner, actions.other]) == before


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
def test_repeated_comparison_reset_preserves_other_group_users_and_favorites(client, actions, kind):
    for group in ("skaters", "goalies"):
        player = actions.create(group)[0]
        player.comparing.add(actions.owner, actions.other)
        player.favoriting.add(actions.owner, actions.other)
    before = state([actions.owner, actions.other])
    for _ in range(2):
        response = client.post(
            reverse("reset_comparison", args=[kind]), query_params={"season": "20262027"}
        )
        assert response.status_code == 200
        assert getattr(actions.owner, "comparable_" + kind).count() == 0
    after = state([actions.owner, actions.other])
    expected = before
    expected[actions.owner.pk]["comparable_" + kind] = []
    assert after == expected


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
@pytest.mark.parametrize("route", ["player_favorite", "player_compare", "reset_comparison"])
@pytest.mark.parametrize("method", ["get", "head"])
def test_saved_mutations_reject_safe_methods_without_changes(client, actions, kind, route, method):
    player = actions.create(kind)[0]
    player.favoriting.add(actions.owner, actions.other)
    player.comparing.add(actions.owner, actions.other)
    before = state([actions.owner, actions.other])
    args = [kind] if route == "reset_comparison" else [player.slug, player.nhl_id]
    url = reverse(route, args=args)
    for authenticated in (True, False):
        if not authenticated:
            client.logout()
        response = getattr(client, method)(url)
        assert response.status_code == 405
        assert response.headers["Allow"] == "POST"
        assert state([actions.owner, actions.other]) == before


@pytest.mark.parametrize("kind", ["skaters", "goalies"])
@pytest.mark.parametrize("route", ["player_favorite", "player_compare", "reset_comparison"])
def test_saved_mutations_require_csrf_and_trusted_origin(actions, kind, route):
    from copy import deepcopy
    from django.test import Client

    players = actions.create(kind, 2)
    opposite = actions.create("goalies" if kind == "skaters" else "skaters")[0]
    for player in [*players, opposite]:
        player.favoriting.add(actions.owner, actions.other)
        player.comparing.add(actions.owner, actions.other)
    before = state([actions.owner, actions.other])
    target = players[0]
    args = [kind] if route == "reset_comparison" else [target.slug, target.nhl_id]
    url = reverse(route, args=args)
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(actions.owner)
    assert strict.post(url).status_code == 403
    assert state([actions.owner, actions.other]) == before
    page = strict.get(reverse("favorites" if route == "player_favorite" else "comparison"))
    assert page.status_code == 200
    assert b'id="ajax-csrf-token"' in page.content
    token = strict.cookies["csrftoken"].value
    for headers in (
        {},
        {"HTTP_X_CSRFTOKEN": "a" * 32},
        {"HTTP_X_CSRFTOKEN": token, "HTTP_ORIGIN": "https://untrusted.invalid"},
    ):
        assert strict.post(url, **headers).status_code == 403
        assert state([actions.owner, actions.other]) == before
    response = strict.post(url, HTTP_X_CSRFTOKEN=token, query_params={"season": "20262027"})
    assert response.status_code == 200
    if route == "reset_comparison":
        assert response.json()[kind + "_count"] == 0
    else:
        assert response.json()["authenticated"] is True
    expected = deepcopy(before)
    relation = ("favorite_" if route == "player_favorite" else "comparable_") + kind
    expected[actions.owner.pk][relation] = [] if route == "reset_comparison" else [players[1].pk]
    assert state([actions.owner, actions.other]) == expected


def concurrent_posts(first_client, first_url, second_client, second_url, *, same_user=True):
    """Hold the first request's real row lock and observe the second DB connection."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic, sleep

    from django.db import connection, connections

    acquired, release, second_connected = Event(), Event(), Event()
    pids = {}

    def post(client, url, first):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[first] = cursor.fetchone()[0]
            if not first:
                second_connected.set()

            def hold_lock(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if first and "FOR UPDATE" in sql:
                    acquired.set()
                    assert release.wait(10), "First request was not released"
                return result

            with connection.execute_wrapper(hold_lock):
                response = client.post(url, query_params={"season": "20262027"})
            assert response.status_code == 200, response.content
            return response.json()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(post, first_client, first_url, True)
        try:
            assert acquired.wait(5), "Mutation never acquired its account lock"
            second = workers.submit(post, second_client, second_url, False)
            assert second_connected.wait(5)
            if same_user:
                deadline = monotonic() + 5
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT %s = ANY(pg_blocking_pids(%s))", [pids[True], pids[False]]
                        )
                        blocked = cursor.fetchone()[0]
                    if blocked:
                        break
                    assert not second.done(), "Second mutation bypassed the account lock"
                    assert monotonic() < deadline, "Second mutation did not wait on the first"
                    sleep(0.01)
            else:
                # A different account must finish while the first account remains locked.
                second.result(timeout=5)
        finally:
            release.set()
        return first.result(timeout=10), second.result(timeout=10)


@pytest.mark.django_db(transaction=True)
class TestConcurrentSavedActions:
    @pytest.fixture
    def clients(self, actions):
        from django.test import Client

        clients = [Client(), Client()]
        for client in clients:
            client.force_login(actions.owner)
        return clients

    @staticmethod
    def url(route, player):
        return reverse(route, args=[player.slug, player.nhl_id])

    @pytest.mark.parametrize(
        "kinds", [("skaters", "skaters"), ("goalies", "goalies"), ("skaters", "goalies")]
    )
    def test_favorites_compete_for_one_shared_slot(self, actions, clients, kinds):
        actions.owner.favorite_skaters.add(*actions.create("skaters", utils.FAVORITES_QUOTA - 2))
        actions.owner.favorite_goalies.add(*actions.create("goalies"))
        candidates = [actions.create(kind)[0] for kind in kinds]
        for player in candidates:
            player.favoriting.add(actions.other)
            player.comparing.add(actions.owner, actions.other)
        before = state([actions.other])
        responses = concurrent_posts(
            clients[0],
            self.url("player_favorite", candidates[0]),
            clients[1],
            self.url("player_favorite", candidates[1]),
        )
        assert "fav_quota_reached" not in responses[0]
        assert responses[1]["fav_quota_reached"] == 1
        assert candidates[0].favoriting.filter(pk=actions.owner.pk).exists()
        assert not candidates[1].favoriting.filter(pk=actions.owner.pk).exists()
        assert (
            actions.owner.favorite_skaters.count() + actions.owner.favorite_goalies.count() == 100
        )
        assert state([actions.other]) == before
        assert (
            actions.owner.comparable_skaters.count() + actions.owner.comparable_goalies.count() == 2
        )

    @pytest.mark.parametrize("kind", ["skaters", "goalies"])
    def test_comparison_contenders_respect_group_limit(self, actions, clients, kind):
        opposite = "goalies" if kind == "skaters" else "skaters"
        getattr(actions.owner, "comparable_" + kind).add(
            *actions.create(kind, utils.COMPARISON_QUOTA - 1)
        )
        getattr(actions.owner, "comparable_" + opposite).add(
            *actions.create(opposite, utils.COMPARISON_QUOTA)
        )
        candidates = actions.create(kind, 2)
        responses = concurrent_posts(
            clients[0],
            self.url("player_compare", candidates[0]),
            clients[1],
            self.url("player_compare", candidates[1]),
        )
        assert "comp_quota_reached" not in responses[0]
        assert responses[1]["comp_quota_reached"] == 1
        assert responses[0][kind + "_count"] == responses[1][kind + "_count"] == 5
        assert getattr(actions.owner, "comparable_" + kind).count() == 5
        assert getattr(actions.owner, "comparable_" + opposite).count() == 5
        assert candidates[0].comparing.filter(pk=actions.owner.pk).exists()
        assert not candidates[1].comparing.filter(pk=actions.owner.pk).exists()

    @pytest.mark.parametrize("kind", ["skaters", "goalies"])
    @pytest.mark.parametrize(
        "route,relation", [("player_favorite", "favoriting"), ("player_compare", "comparing")]
    )
    def test_same_player_toggles_run_in_order(self, actions, clients, kind, route, relation):
        player = actions.create(kind)[0]
        getattr(player, relation).add(actions.other)
        before = state([actions.owner, actions.other])
        before_player = type(player).objects.values().get(pk=player.pk)
        responses = concurrent_posts(
            clients[0], self.url(route, player), clients[1], self.url(route, player)
        )
        assert "successfully added" in responses[0]["message"]
        assert "successfully removed" in responses[1]["message"]
        assert state([actions.owner, actions.other]) == before
        assert type(player).objects.values().get(pk=player.pk) == before_player

    @pytest.mark.parametrize("kind", ["skaters", "goalies"])
    @pytest.mark.parametrize("reset_first", [True, False])
    def test_reset_and_toggle_share_the_lock(self, actions, clients, kind, reset_first):
        players = actions.create(kind, utils.COMPARISON_QUOTA)
        getattr(actions.owner, "comparable_" + kind).add(*players)
        candidate = actions.create(kind)[0]
        candidate.favoriting.add(actions.owner, actions.other)
        candidate.comparing.add(actions.other)
        before_other = state([actions.other])
        reset = reverse("reset_comparison", args=[kind])
        add = self.url("player_compare", candidate)
        urls = [reset, add] if reset_first else [add, reset]
        responses = concurrent_posts(clients[0], urls[0], clients[1], urls[1])
        assert responses[0][kind + "_count"] == (0 if reset_first else 5)
        assert responses[1][kind + "_count"] == (1 if reset_first else 0)
        assert list(getattr(actions.owner, "comparable_" + kind).values_list("pk", flat=True)) == (
            [candidate.pk] if reset_first else []
        )
        assert candidate.favoriting.filter(pk=actions.owner.pk).exists()
        assert state([actions.other]) == before_other

    @pytest.mark.parametrize("kind", ["skaters", "goalies"])
    @pytest.mark.parametrize(
        "route,relation,limit",
        [
            ("player_favorite", "favorite_", utils.FAVORITES_QUOTA),
            ("player_compare", "comparable_", utils.COMPARISON_QUOTA),
        ],
    )
    def test_removal_frees_slot_for_waiting_add(
        self, actions, clients, kind, route, relation, limit
    ):
        players = actions.create(kind, limit)
        manager = getattr(actions.owner, relation + kind)
        manager.add(*players)
        candidate = actions.create(kind)[0]
        responses = concurrent_posts(
            clients[0], self.url(route, players[0]), clients[1], self.url(route, candidate)
        )
        assert "successfully removed" in responses[0]["message"]
        assert "successfully added" in responses[1]["message"]
        assert manager.count() == limit
        assert not manager.filter(pk=players[0].pk).exists()
        assert manager.filter(pk=candidate.pk).exists()

    @pytest.mark.parametrize(
        "route,relation", [("player_favorite", "favoriting"), ("player_compare", "comparing")]
    )
    def test_different_accounts_do_not_block_each_other(self, actions, clients, route, relation):
        clients[1].force_login(actions.other)
        player = actions.create("skaters")[0]
        concurrent_posts(
            clients[0],
            self.url(route, player),
            clients[1],
            self.url(route, player),
            same_user=False,
        )
        assert set(getattr(player, relation).values_list("pk", flat=True)) == {
            actions.owner.pk,
            actions.other.pk,
        }

    @pytest.mark.parametrize("kind", ["skaters", "goalies"])
    @pytest.mark.parametrize("route", ["player_compare", "reset_comparison"])
    def test_failure_rolls_back_membership_and_releases_lock(
        self, actions, clients, kind, route, monkeypatch
    ):
        from players import saved_players

        player = actions.create(kind)[0]
        player.comparing.add(actions.owner, actions.other)
        before = state([actions.owner, actions.other])
        url = (
            reverse(route, args=[kind]) if route == "reset_comparison" else self.url(route, player)
        )
        original = saved_players.comparison_payload

        def fail(*args):
            raise RuntimeError("Payload rendering failed")

        monkeypatch.setattr(saved_players, "comparison_payload", fail)
        with pytest.raises(RuntimeError, match="Payload rendering failed"):
            clients[0].post(url, query_params={"season": "20262027"})
        assert state([actions.owner, actions.other]) == before
        monkeypatch.setattr(saved_players, "comparison_payload", original)
        assert clients[1].post(url, query_params={"season": "20262027"}).status_code == 200
        assert not player.comparing.filter(pk=actions.owner.pk).exists()
        assert player.comparing.filter(pk=actions.other.pk).exists()
