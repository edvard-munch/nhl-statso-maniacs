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
    return client.get(
        reverse(route, args=[player.slug, player.nhl_id]), {"season": "20262027", **params}
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
    response = client.get(
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
        response = client.get(reverse("reset_comparison", args=[kind]), {"season": "20262027"})
        assert response.status_code == 200
        assert getattr(actions.owner, "comparable_" + kind).count() == 0
    after = state([actions.owner, actions.other])
    expected = before
    expected[actions.owner.pk]["comparable_" + kind] = []
    assert after == expected
