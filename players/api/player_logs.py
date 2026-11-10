"""Saved player gamelogs using the same identity checks as game detail."""

from collections import Counter
from datetime import date
import re

from django.db.models import Exists, OuterRef, Prefetch, Q
from django.utils import timezone

from players.models import Game, Side
from .game_detail import (
    ROSTER_GROUPS,
    SKATER_COUNTS,
    SKATER_TIMES,
    game_player,
    goalie_stats,
    skater_stats,
)
from .profiles import player_model
from .scoreboard import game_summary

REGULAR_GAME_ID = re.compile(r"([0-9]{4})02[0-9]{4}")
DATE_KEY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
SEASON_YEAR_SPAN = 1
SKATER_LOG_NUMBERS = frozenset({*SKATER_COUNTS, *SKATER_TIMES})
GOALIE_LOG_NUMBERS = frozenset(
    {"toi_seconds", "goals_against", "saves", "shots_against", "save_percentage", "shutouts"}
)
ALL_LOG_NUMBERS = SKATER_LOG_NUMBERS | GOALIE_LOG_NUMBERS
LOG_IDENTITIES = frozenset({"date", "game_id", "team_abbr", "opponent_abbr"})


def numeric_fields(player_type):
    return GOALIE_LOG_NUMBERS if player_type == "goalie" else SKATER_LOG_NUMBERS


def ordering_fields(player_type):
    return (
        numeric_fields(player_type)
        | LOG_IDENTITIES
        | ({"decision"} if player_type == "goalie" else set())
    )


def log_date(key):
    if not isinstance(key, str) or not DATE_KEY.fullmatch(key):
        return None
    try:
        return date.fromisoformat(key)
    except ValueError:
        return None


def game_season(nhl_id):
    match = REGULAR_GAME_ID.fullmatch(str(nhl_id))
    return f"{match[1]}{int(match[1]) + SEASON_YEAR_SPAN:04d}" if match else None


def gamelog(player, player_type, query):
    model = player_model(player_type)
    relations = [
        (side, relation) for side, _, group_model, relation in ROSTER_GROUPS if group_model is model
    ]
    annotations = {}
    for side, relation in relations:
        through = Game._meta.get_field(relation).remote_field.through
        annotations["api_" + relation] = Exists(
            through.objects.filter(
                game_id=OuterRef("pk"), **{model._meta.model_name + "_id": player.pk}
            )
        )
    membership = Q()
    for name in annotations:
        membership |= Q(**{name: True})
    games = list(
        Game.objects.select_related("gameday")
        .annotate(**annotations)
        .filter(membership)
        .prefetch_related(
            Prefetch(
                "side_set",
                queryset=Side.objects.select_related("team").order_by("pk"),
                to_attr="scoreboard_sides",
            )
        )
    )
    counts = Counter(game.gameday_id for game in games if game.gameday_id is not None)
    logs = player.gamelog_stats if isinstance(player.gamelog_stats, dict) else {}
    represented = set()
    rows = []
    checked_at = timezone.now()
    for game in games:
        day = game.gameday.day if game.gameday else None
        if day:
            represented.add(day.isoformat())
        groups = [side for side, relation in relations if getattr(game, "api_" + relation)]
        side = groups[0] if len(groups) == 1 else None
        summary = game_summary(game, day, checked_at)
        player.api_game_stats = logs.get(day.isoformat()) if day else None
        collisions = {model: {player.pk} if counts[game.gameday_id] > 1 else set()}
        entry = game_player(
            player,
            model,
            game,
            side or "away",
            summary,
            collisions,
            Counter({(model, player.nhl_id): len(groups)}),
        )
        rows.append(
            {
                "date": day,
                "game": summary,
                "side": side,
                "team": summary[side + "_team"] if side else None,
                "opponent": summary[("home" if side == "away" else "away") + "_team"]
                if side
                else None,
                **{
                    field: entry[field]
                    for field in ("stats", "game_position", "sweater_number", "availability")
                },
            }
        )
    for key, raw in logs.items():
        day = log_date(key)
        if day is None or key in represented:
            continue
        rows.append(
            {
                "date": day,
                "game": None,
                "side": None,
                "team": None,
                "opponent": None,
                "game_position": None,
                "sweater_number": None,
                "availability": "unverified" if isinstance(raw, dict) else "missing",
                "stats": goalie_stats({}) if player_type == "goalie" else skater_stats({}),
            }
        )
    if "season_id" in query:
        rows = [
            row
            for row in rows
            if row["game"] and game_season(row["game"]["nhl_id"]) == query["season_id"]
        ]
    for suffix in ("min", "max"):
        key = "date_" + suffix
        if key in query:
            rows = [
                row
                for row in rows
                if row["date"] is not None
                and (row["date"] >= query[key] if suffix == "min" else row["date"] <= query[key])
            ]
    for team_key in ("team", "opponent"):
        if team_key in query:
            rows = [
                row for row in rows if row[team_key] and row[team_key]["abbr"] in query[team_key]
            ]
    for field in numeric_fields(player_type):
        for suffix in ("min", "max", "isnull"):
            key = field + "_" + suffix
            if key not in query:
                continue
            rows = [row for row in rows if matches(row["stats"][field], suffix, query[key])]
    rows.sort(
        key=lambda row: (row["date"] or date.min, row["game"]["nhl_id"] if row["game"] else 0)
    )
    for term in reversed(query["ordering"].split(",")):
        field = term.removeprefix("-")
        known = [row for row in rows if ordered_value(row, field) is not None]
        unknown = [row for row in rows if ordered_value(row, field) is None]
        rows = (
            sorted(known, key=lambda row: ordered_value(row, field), reverse=term.startswith("-"))
            + unknown
        )
    return rows


def matches(value, suffix, bound):
    if suffix == "isnull":
        return (value is None) == bound
    return value is not None and (value >= bound if suffix == "min" else value <= bound)


def ordered_value(row, field):
    if field == "date":
        return row["date"]
    if field == "game_id":
        return row["game"]["nhl_id"] if row["game"] else None
    if field in ("team_abbr", "opponent_abbr"):
        team = row[field.removesuffix("_abbr")]
        return team["abbr"].casefold() if team else None
    return row["stats"][field]
