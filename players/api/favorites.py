"""Private saved season rows and explicit membership changes under the owner lock."""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound

from nhl_web_app.api.errors import FavoritesQuotaExceeded
from players.models import Team
from players.utils import FAVORITES_QUOTA
from .catalogue import (
    IDENTITY_FIELDS,
    DEFAULT_ORDERING,
    matches,
    ordered_rows,
    participating_teams,
    public_identity,
    resolve_season,
)
from .profiles import MAX_PLAYER_NHL_ID, player_model, season_packet


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
    """The caller holds saved_actions.locked_user through response serialization."""
    season = resolve_season(query)
    player_type, mode = query["player_type"], query["mode"]
    ordering = query.get("ordering", DEFAULT_ORDERING[player_type])
    teams = (
        {team.abbr: team for team in Team.objects.only("nhl_id", "abbr", "name", "slug")}
        if season
        else {}
    )
    candidates = getattr(owner, FAVORITE_RELATIONS[player_type]).only(*IDENTITY_FIELDS, "sbs_stats")
    rows = []
    for player in candidates:
        saved = season_packet(player.sbs_stats, season, player_type, mode)
        row = {
            **public_identity(player),
            "player_type": player_type,
            **saved,
            "teams": participating_teams(player.sbs_stats, season, teams)
            if saved["stats"] is not None
            else [],
        }
        if matches(row, query):
            rows.append(row)
    return ordered_rows(rows, ordering), {
        "season_id": season,
        "player_type": player_type,
        "mode": mode,
        "ordering": ordering,
        "quota": quota(owner),
    }


def membership_target(player_type, nhl_id):
    model = player_model(player_type)
    if not 0 < nhl_id <= MAX_PLAYER_NHL_ID:
        raise NotFound()
    return model


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
