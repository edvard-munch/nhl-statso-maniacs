"""Private saved season rows and explicit membership changes under the owner lock."""

from django.shortcuts import get_object_or_404
from players.utils import FAVORITES_QUOTA
from nhl_web_app.api.errors import FavoritesQuotaExceeded
from .saved_lists import saved_rows


FAVORITE_RELATIONS = {"skater": "favorite_skaters", "goalie": "favorite_goalies"}


def quota(owner):
    skaters = owner.favorite_skaters.count()
    goalies = owner.favorite_goalies.count()
    total = skaters + goalies
    return {
        "limit": FAVORITES_QUOTA,
        "skaters_count": skaters,
        "goalies_count": goalies,
        "total_count": total,
        "remaining": max(0, FAVORITES_QUOTA - total),
        "over_limit": total > FAVORITES_QUOTA,
    }


def favorite_rows(owner, query):
    rows, meta = saved_rows(owner, query, FAVORITE_RELATIONS[query["player_type"]])
    return rows, {**meta, "quota": quota(owner)}


def put_membership(owner, model, player_type, nhl_id):
    """All state reads/counts/writes happen inside the caller's owner transaction."""
    player = get_object_or_404(model.objects.only("nhl_id"), nhl_id=nhl_id)
    relation = getattr(owner, FAVORITE_RELATIONS[player_type])
    if relation.filter(pk=player.pk).exists():
        created = False
    else:
        current = quota(owner)
        if current["total_count"] >= current["limit"]:
            raise FavoritesQuotaExceeded()
        relation.add(player)
        created = True
    return {
        "player_type": player_type,
        "nhl_id": nhl_id,
        "is_favorite": True,
        "quota": quota(owner),
    }, created


def delete_membership(owner, model, player_type, nhl_id):
    player = model.objects.only("nhl_id").filter(nhl_id=nhl_id).first()
    if player is not None:
        getattr(owner, FAVORITE_RELATIONS[player_type]).remove(player)
