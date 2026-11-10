"""Verified saved-game rosters/statistics, with no upstream or presentation work."""

from collections import Counter
import math
import re

from django.db.models import JSONField, Prefetch, Value, prefetch_related_objects
from django.db.models.fields.json import KeyTransform
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound

from players.models import Game, Goalie, Side, Skater
from .scoreboard import _freshness, game_summary

MAX_INTEGER = 2**31 - 1
SECONDS_PER_MINUTE = 60
INTEGER = re.compile(r"-?[0-9]+")
DURATION = re.compile(r"([0-9]+):([0-5][0-9])")
SAVE_PAIR = re.compile(r"([0-9]+)/([0-9]+)")
MAX_INTEGER_DIGITS = len(str(MAX_INTEGER))
PLAYER_FIELDS = ("nhl_id", "name", "slug", "last_name", "position_abbr")
ROSTER_GROUPS = (
    ("away", "forwards", Skater, "away_forwards"),
    ("away", "defencemen", Skater, "away_defencemen"),
    ("away", "goalies", Goalie, "away_goalies"),
    ("home", "forwards", Skater, "home_forwards"),
    ("home", "defencemen", Skater, "home_defencemen"),
    ("home", "goalies", Goalie, "home_goalies"),
)
SKATER_COUNTS = {
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "plus_minus": "plusMinus",
    "penalty_minutes": "pim",
    "shots_on_goal": "sog",
    "hits": "hits",
    "blocked_shots": "blockedShots",
    "faceoffs_won": "faceoffs",
    "pp_points": "powerPlayPoints",
    "sh_points": "shPoints",
}
SKATER_TIMES = {
    "toi_seconds": "toi",
    "pp_toi_seconds": "powerPlayToi",
    "sh_toi_seconds": "shorthandedToi",
}
GAME_POSITIONS = frozenset({"C", "L", "R", "LW", "RW", "D", "G"})
DECISIONS = frozenset({"W", "L", "O", "OT"})


def integer(value, *, signed=False):
    if isinstance(value, str):
        if len(value.lstrip("-")) > MAX_INTEGER_DIGITS or INTEGER.fullmatch(value) is None:
            return None
        value = int(value)
    if type(value) is not int or not (-MAX_INTEGER if signed else 0) <= value <= MAX_INTEGER:
        return None
    return value


def duration(value):
    match = DURATION.fullmatch(value) if isinstance(value, str) else None
    minutes = integer(match[1]) if match else None
    if minutes is None:
        return None
    return integer(minutes * SECONDS_PER_MINUTE + int(match[2]))


def save_percentage(value):
    if type(value) not in (int, float, str):
        return None
    try:
        value = float(value)
    except (ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def skater_stats(row):
    return {
        **{
            field: integer(row.get(source), signed=field == "plus_minus")
            for field, source in SKATER_COUNTS.items()
        },
        **{field: duration(row.get(source)) for field, source in SKATER_TIMES.items()},
    }


def goalie_stats(row):
    pair = (
        SAVE_PAIR.fullmatch(row.get("saveShotsAgainst", ""))
        if isinstance(row.get("saveShotsAgainst"), str)
        else None
    )
    saves = integer(row["saves"]) if "saves" in row else integer(pair[1]) if pair else None
    shots = (
        integer(row["shotsAgainst"])
        if "shotsAgainst" in row
        else integer(pair[2])
        if pair
        else None
    )
    if saves is not None and shots is not None and saves > shots:
        saves = shots = None
    shutouts = integer(row.get("shutout"))
    return {
        "decision": row.get("decision")
        if isinstance(row.get("decision"), str) and row["decision"] in DECISIONS
        else None,
        "toi_seconds": duration(row.get("toi")),
        "goals_against": integer(row.get("goalsAgainst")),
        "saves": saves,
        "shots_against": shots,
        "save_percentage": save_percentage(row.get("savePctg")),
        "shutouts": shutouts if shutouts in (0, 1) else None,
    }


def _legacy_collisions(game, groups):
    collisions = {}
    for model in (Skater, Goalie):
        ids = {
            p.pk
            for _, _, group_model, relation in ROSTER_GROUPS
            if group_model is model
            for p in groups[relation]
            if isinstance(p.api_game_stats, dict) and "gameId" not in p.api_game_stats
        }
        if not ids or game.gameday_id is None:
            collisions[model] = set()
            continue
        queries = []
        player_field = model._meta.model_name + "_id"
        for _, _, group_model, relation in ROSTER_GROUPS:
            if group_model is model:
                through = Game._meta.get_field(relation).remote_field.through
                queries.append(
                    through.objects.filter(
                        game__gameday_id=game.gameday_id, **{player_field + "__in": ids}
                    )
                    .exclude(game_id=game.pk)
                    .values_list(player_field, flat=True)
                )
        collisions[model] = set(queries[0].union(*queries[1:]))
    return collisions


def _verified(row, player, model, game, side, summary, collisions, appearances):
    identity = row.get("player")
    if not isinstance(identity, dict) or integer(identity.get("nhl_id")) != player.nhl_id:
        return False
    if appearances[(model, player.nhl_id)] != 1:
        return False
    position = row.get("position")
    if position is not None and (
        (model is Goalie and position != "G") or (model is Skater and position == "G")
    ):
        return False
    if "gameId" in row:
        return integer(row["gameId"]) == game.nhl_id
    team, opponent = (
        summary[side + "_team"],
        summary[("home" if side == "away" else "away") + "_team"],
    )
    return bool(
        team
        and opponent
        and team["nhl_id"] != opponent["nhl_id"]
        and team["abbr"]
        and opponent["abbr"]
        and team["abbr"] != opponent["abbr"]
        and isinstance(row.get("team"), dict)
        and isinstance(row.get("opponent"), dict)
        and row["team"].get("abbr") == team["abbr"]
        and row["opponent"].get("abbr") == opponent["abbr"]
        and player.pk not in collisions[model]
    )


def game_player(player, model, game, side, summary, collisions, appearances):
    row = player.api_game_stats
    availability = "missing" if not isinstance(row, dict) else "complete"
    if isinstance(row, dict) and not _verified(
        row, player, model, game, side, summary, collisions, appearances
    ):
        availability = "unverified"
    source = row if availability == "complete" else {}
    stats = goalie_stats(source) if model is Goalie else skater_stats(source)
    sweater = integer(source.get("sweaterNumber"))
    position = source.get("position")
    position = position if isinstance(position, str) and position in GAME_POSITIONS else None
    if availability == "complete" and (
        any(value is None for value in stats.values()) or sweater is None or position is None
    ):
        availability = "partial"
    return {
        "player_type": "goalie" if model is Goalie else "skater",
        "nhl_id": player.nhl_id,
        "name": player.name,
        "last_name": player.last_name,
        "slug": player.slug,
        "position_abbr": player.position_abbr,
        "game_position": position,
        "sweater_number": sweater,
        "availability": availability,
        "stats": stats,
    }


def game_detail(nhl_id):
    if not 1 <= nhl_id <= MAX_INTEGER:
        raise NotFound()
    game = get_object_or_404(
        Game.objects.select_related("gameday").prefetch_related(
            Prefetch(
                "side_set",
                queryset=Side.objects.select_related("team").order_by("pk"),
                to_attr="scoreboard_sides",
            )
        ),
        nhl_id=nhl_id,
    )
    day = game.gameday.day if game.gameday else None
    date_stats = (
        KeyTransform(day.isoformat(), "gamelog_stats")
        if day
        else Value(None, output_field=JSONField())
    )
    prefetch_related_objects(
        [game],
        *[
            Prefetch(
                relation,
                queryset=model.objects.only(*PLAYER_FIELDS)
                .annotate(api_game_stats=date_stats)
                .order_by("last_name", "nhl_id"),
                to_attr="api_" + relation,
            )
            for _, _, model, relation in ROSTER_GROUPS
        ],
    )
    groups = {relation: getattr(game, "api_" + relation) for _, _, _, relation in ROSTER_GROUPS}
    appearances = Counter(
        (model, player.nhl_id)
        for _, _, model, relation in ROSTER_GROUPS
        for player in groups[relation]
    )
    collisions = _legacy_collisions(game, groups)
    checked_at = timezone.now()
    result = game_summary(game, day, checked_at)
    rosters = {"away": {}, "home": {}}
    for side, group, model, relation in ROSTER_GROUPS:
        rosters[side][group] = [
            game_player(p, model, game, side, result, collisions, appearances)
            for p in groups[relation]
        ]
    partial = (
        result["freshness"]["partial"]
        or day is None
        or any(
            not (roster["forwards"] or roster["defencemen"])
            or not roster["goalies"]
            or any(p["availability"] != "complete" for group in roster.values() for p in group)
            for roster in rosters.values()
        )
    )
    result.update(rosters=rosters, freshness=_freshness([game], checked_at, partial=partial))
    return result
