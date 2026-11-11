"""Saved scoreboard projection; no loaders, upstream calls or HTML rendering."""

import re
from typing import NamedTuple

from django.db.models import Prefetch
from django.utils import timezone

from players.game_refresh import freshness
from players.models import Game, Side
from .game_state import LEGACY_RESULT_SOURCE, state_evidence

AWAY = "away"
HOME = "home"
# Exact suffixes currently emitted by upd_gms.get_score; arbitrary legacy text
# and reordered/renamed/ambiguous teams must not become guessed scores.
SAVED_SCORE = re.compile(
    r"(0|[1-9][0-9]*):(0|[1-9][0-9]*)(?:(?P<live> \(Live\))| (?P<outcome>OT|SO))?"
)
SCORE_SOURCE = LEGACY_RESULT_SOURCE


class SavedScore(NamedTuple):
    away: int
    home: int
    outcome: str | None
    is_live: bool


def _team(side):
    if side is None:
        return None
    team = side.team
    return {"nhl_id": team.nhl_id, "name": team.name, "abbr": team.abbr, "slug": team.slug}


def _scores(game, sides):
    if len(sides) != 2 or {side.side for side in sides} != {AWAY, HOME}:
        return None
    by_side = {side.side: side for side in sides}
    away, home = by_side[AWAY].team, by_side[HOME].team
    if away.nhl_id == home.nhl_id:
        return None
    prefix = f"{away.name} - {home.name} "
    if not game.result.startswith(prefix):
        return None
    match = SAVED_SCORE.fullmatch(game.result[len(prefix) :])
    return (
        SavedScore(int(match[1]), int(match[2]), match["outcome"], match["live"] is not None)
        if match
        else None
    )


def _freshness(games, checked_at, *, partial=False, kind="game"):
    saved = freshness(games, partial=partial, kind=kind, checked_at=checked_at)
    return {
        "has_data": saved["has_data"],
        "is_final": saved["final"],
        "saved_at": saved["saved_at"],
        "checked_at": saved["checked_at"],
        "age_seconds": saved["age_seconds"],
        "stale_after_seconds": saved["stale_after_seconds"],
        "is_stale": not saved["final"]
        and saved["age_seconds"] is not None
        and saved["age_seconds"] >= saved["stale_after_seconds"],
        "partial": partial,
    }


def scoreboard(day):
    checked_at = timezone.now()
    games = list(
        Game.objects.filter(gameday__day=day)
        .order_by("nhl_id")
        .prefetch_related(
            Prefetch(
                "side_set",
                queryset=Side.objects.select_related("team").order_by("pk"),
                to_attr="scoreboard_sides",
            )
        )
    )
    rows = [game_summary(game, day, checked_at) for game in games]
    return rows, {
        "date": day,
        "freshness": _freshness(
            games,
            checked_at,
            partial=any(row["freshness"]["partial"] for row in rows),
            kind="scoreboard",
        ),
    }


def game_summary(game, day, checked_at):
    """Project a saved game with prefetched scoreboard_sides, without queries."""
    sides = game.scoreboard_sides
    scores = _scores(game, sides)
    teams = {}
    for label in (AWAY, HOME):
        matches = [side for side in sides if side.side == label]
        teams[label] = _team(matches[0]) if len(matches) == 1 else None
    return {
        "nhl_id": game.nhl_id,
        "slug": game.slug,
        "date": day,
        "is_final": game.game_finished,
        "state": state_evidence(
            game.game_finished,
            is_live=scores.is_live if scores else False,
            final_result=scores is not None and scores.outcome is not None,
        ),
        "away_team": teams[AWAY],
        "home_team": teams[HOME],
        "away_score": scores.away if scores else None,
        "home_score": scores.home if scores else None,
        "score_outcome": scores.outcome if scores else None,
        "score_source": SCORE_SOURCE if scores else None,
        "freshness": _freshness([game], checked_at, partial=scores is None),
    }
