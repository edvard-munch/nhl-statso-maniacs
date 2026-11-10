"""Comparison selections with independent typed quotas under the existing owner lock."""

from django.shortcuts import get_object_or_404

from nhl_web_app.api.errors import ComparisonQuotaExceeded
from players.utils import COMPARISON_QUOTA
from .saved_lists import saved_rows

COMPARISON_RELATIONS = {"skater": "comparable_skaters", "goalie": "comparable_goalies"}


def quota(owner):
    result = {"limit_per_type": COMPARISON_QUOTA}
    for player_type, relation in COMPARISON_RELATIONS.items():
        count = getattr(owner, relation).count()
        result[player_type + "s"] = {
            "count": count,
            "remaining": max(0, COMPARISON_QUOTA - count),
            "over_limit": count > COMPARISON_QUOTA,
        }
    return result


def comparison_rows(owner, query):
    rows, meta = saved_rows(
        owner, query, COMPARISON_RELATIONS[query["player_type"]], scope=query["scope"]
    )
    return rows, {**meta, "scope": query["scope"], "quota": quota(owner)}


def put_membership(owner, model, player_type, nhl_id):
    player = get_object_or_404(model.objects.only("nhl_id"), nhl_id=nhl_id)
    relation = getattr(owner, COMPARISON_RELATIONS[player_type])
    created = not relation.filter(pk=player.pk).exists()
    if created:
        if relation.count() >= COMPARISON_QUOTA:
            raise ComparisonQuotaExceeded()
        relation.add(player)
    return {
        "player_type": player_type,
        "nhl_id": nhl_id,
        "is_compared": True,
        "quota": quota(owner),
    }, created


def delete_membership(owner, model, player_type, nhl_id):
    player = model.objects.only("nhl_id").filter(nhl_id=nhl_id).first()
    if player is not None:
        getattr(owner, COMPARISON_RELATIONS[player_type]).remove(player)


def clear_memberships(owner, player_type):
    getattr(owner, COMPARISON_RELATIONS[player_type]).clear()
