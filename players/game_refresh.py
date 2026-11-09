"""Read-only saved-game freshness; browser checks never fetch NHL data."""

from django.template.loader import render_to_string
from django.utils import timezone

from .models import Game

STALE_AFTER_SECONDS = 15 * 60
SUPPLEMENTARY_FIELDS = ("faceoffs", "powerPlayPoints", "shPoints", "powerPlayToi", "shorthandedToi")


GOALIE_FIELDS = ("toi", "goalsAgainst", "savePctg", "saveShotsAgainst")


def freshness(games, *, partial=False, kind="game", checked_at=None):
    now = checked_at or timezone.now()
    unfinished = [game for game in games if not game.game_finished]
    saved = min((game.updated_date for game in unfinished), default=None)
    if saved is None:
        saved = max((game.updated_date for game in games), default=None)
    meta = {
        "kind": kind,
        "has_data": bool(games),
        "final": bool(games) and not unfinished,
        "saved_at": saved.isoformat() if saved else None,
        "checked_at": now.isoformat(),
        "age_seconds": max(0, (now - saved).total_seconds()) if saved else None,
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "partial": partial,
    }
    meta["text"] = description(meta)
    return meta


def description(meta):
    if not meta["has_data"]:
        return "No saved game data yet."
    label = (
        "Scoreboard" if meta["kind"] == "scoreboard" else "Final" if meta["final"] else "Not final"
    )
    parts = [label + ".", "Data saved " + meta["saved_at"] + "."]
    if not meta["final"] and meta["age_seconds"] >= meta["stale_after_seconds"]:
        parts.append("Data may be out of date.")
    if meta["partial"]:
        parts.append("Some player or supplementary statistics are unavailable.")
    return " ".join(parts)


def game_meta(context):
    game = context["game"]
    date = str(game.gameday.day) if game.gameday else None
    skaters = [player for item in context["skaters"] for player in item["list"]]
    partial = not skaters
    for player in skaters:
        row = player.gamelog_stats.get(date) if isinstance(player.gamelog_stats, dict) else None
        if not isinstance(row, dict) or any(
            row.get(field) in (None, "") for field in SUPPLEMENTARY_FIELDS
        ):
            partial = True
    for item in context["skaters"]:
        for player in item.get("game_goalies_table", {}).get("list", []):
            row = player.gamelog_stats.get(date) if isinstance(player.gamelog_stats, dict) else None
            if not isinstance(row, dict) or any(
                row.get(field) in (None, "") for field in GOALIE_FIELDS
            ):
                partial = True
    return freshness([game], partial=partial)


def game_payload(context, request):
    tables = {}
    for item in context["skaters"]:
        row_context = {**context, "item": item}
        tables[item["table_id"]] = render_to_string(
            "players/partial_game_detail_tbody.html", row_context, request=request
        )
        if item.get("game_goalies_table"):
            tables[item["game_goalies_table"]["id"]] = render_to_string(
                "players/partial_game_goalies_tbody.html", row_context, request=request
            )
    return {
        "entity": f"game:{context['game'].nhl_id}",
        "result": context["game"].result,
        "tables": tables,
        "freshness": context["freshness"],
    }


def scoreboard_context(date):
    games = list(Game.objects.filter(gameday__day=date).order_by("nhl_id"))
    return {
        "scoreboard_games": [{"game": game, "freshness": freshness([game])} for game in games],
        "freshness": freshness(games, kind="scoreboard"),
    }
