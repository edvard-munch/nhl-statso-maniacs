"""Compare saved game PP/SH time with current NHL sources without writing data."""

from datetime import date
import json
import re

import requests
from django.core.management.base import BaseCommand, CommandError

from players.models import Game, Goalie, Skater
from . import upd_gms


SEASON_PATTERN = r"^(\d{4})(\d{4})$"
GAME_YEAR_MULTIPLIER = 1_000_000
REGULAR_GAME_START = 20_000
REGULAR_GAME_END = 30_000
TOI_FIELDS = ("powerPlayToi", "shorthandedToi")
REPORT_SIDES = (("toiAway", "awayTeam"), ("toiHome", "homeTeam"))
STATUSES = ("match", "mismatch", "unverified")


def toi_seconds(value):
    if not isinstance(value, str) or not re.fullmatch(upd_gms.TIME_MM_SS_REGEX, value):
        return None
    minutes, seconds = map(int, value.split(":"))
    return minutes * 60 + seconds if seconds < 60 else None


def select_games(options):
    games = Game.objects.select_related("gameday").order_by("gameday__day", "nhl_id")
    season = options["season"]
    start, end = options["start_date"], options["end_date"]
    if not season and not options["game_id"] and not (start and end):
        raise CommandError("Select --season, --game-id, or both --start-date and --end-date.")
    if season:
        match = re.fullmatch(SEASON_PATTERN, season)
        if not match or int(match[2]) != int(match[1]) + 1:
            raise CommandError("--season must be consecutive years, for example 20262027.")
        year = int(match[1]) * GAME_YEAR_MULTIPLIER
        games = games.filter(
            nhl_id__gte=year + REGULAR_GAME_START, nhl_id__lt=year + REGULAR_GAME_END
        )
    try:
        start = date.fromisoformat(start) if start else None
        end = date.fromisoformat(end) if end else None
    except ValueError as error:
        raise CommandError("Dates must use YYYY-MM-DD.") from error
    if start and end and start > end:
        raise CommandError("--start-date must not follow --end-date.")
    if start:
        games = games.filter(gameday__day__gte=start)
    if end:
        games = games.filter(gameday__day__lte=end)
    if options["game_id"]:
        games = games.filter(nhl_id__in=options["game_id"])
    return games


def audit_game(game, session):
    """Return field comparisons; missing/unreadable evidence never becomes zero."""
    records = []
    day = str(game.gameday.day) if game.gameday else None

    def record(status, reason=None, **details):
        records.append(dict(game_id=game.nhl_id, date=day, status=status, **details))
        if reason:
            records[-1]["reason"] = reason

    if day is None:
        record("unverified", "Saved game has no gameday")
        return records
    try:
        boxscore = upd_gms.get_game_data(game.nhl_id, upd_gms.URL_BOXSCORE, session)
        if boxscore["gameState"] not in upd_gms.FINAL_GAME_STATES:
            record("unverified", "NHL game is not final")
            return records
        if boxscore.get("id") != game.nhl_id or boxscore.get("gameDate") != day:
            record("unverified", "Boxscore game ID/date does not match saved game")
            return records
        links = upd_gms.get_game_report_links(game.nhl_id, session)
    except (CommandError, requests.RequestException, ValueError) as error:
        record("unverified", str(error))
        return records

    for report_key, side in REPORT_SIDES:
        roster = list(upd_gms.report_roster_players(boxscore, side))
        if not roster:
            record("unverified", "Missing played roster", side=side)
            continue
        html = upd_gms.fetch_report_html(links.get(report_key), session)
        parsed = upd_gms.parse_toi_report(html)
        sweaters = upd_gms.map_report_sweaters_to_players(boxscore, side)
        by_id = upd_gms.resolve_report_players(parsed, sweaters, report_key)
        ids = [p.get("playerId") for p in roster]
        saved = {}
        for model in (Skater, Goalie):
            for player in model.objects.filter(nhl_id__in=ids):
                saved.setdefault(player.nhl_id, []).append(player)
        for api_player in roster:
            player_id = api_player.get("playerId")
            candidates = saved.get(player_id, [])
            details = dict(side=side, player_id=player_id)
            if len(candidates) != 1:
                record("unverified", "Missing or ambiguous saved player", **details)
                continue
            player = candidates[0]
            details["player"] = player.name
            logs = player.gamelog_stats
            log = logs.get(day) if isinstance(logs, dict) else None
            if not isinstance(log, dict):
                record("unverified", "Missing saved gamelog", **details)
                continue
            for field in TOI_FIELDS:
                # Match loader precedence: a present boxscore value wins.
                expected = api_player.get(field)
                source = "boxscore"
                if expected in (None, ""):
                    expected = by_id.get(player_id, {}).get(field)
                    source = report_key
                stored = log.get(field)
                values = dict(field=field, stored=stored, expected=expected, source=source)
                if toi_seconds(expected) is None:
                    record("unverified", "Missing or invalid source TOI", **details, **values)
                else:
                    status = "match" if toi_seconds(stored) == toi_seconds(expected) else "mismatch"
                    record(status, **details, **values)
    return records


class Command(BaseCommand):
    help = "Read-only audit of saved game PP/SH TOI against NHL boxscores and reports."

    def add_arguments(self, parser):
        parser.add_argument("--season", help="Regular-season ID, e.g. 20262027")
        parser.add_argument("--start-date", help="Inclusive YYYY-MM-DD")
        parser.add_argument("--end-date", help="Inclusive YYYY-MM-DD")
        parser.add_argument("--game-id", type=int, action="append", help="Repeat to select games")
        parser.add_argument("--json", action="store_true", dest="json_output")

    def handle(self, *args, **options):
        games = select_games(options)
        records = []
        game_count = 0
        with requests.Session() as session:
            for game in games.iterator():
                game_count += 1
                records.extend(audit_game(game, session))
        summary = {status: sum(r["status"] == status for r in records) for status in STATUSES}
        summary["games"] = game_count
        summary["games_with_mismatches"] = len(
            {r["game_id"] for r in records if r["status"] == "mismatch"}
        )
        summary["games_unverified"] = len(
            {r["game_id"] for r in records if r["status"] == "unverified"}
        )
        if options["json_output"]:
            self.stdout.write(json.dumps(dict(summary=summary, records=records)))
        else:
            for row in records:
                if row["status"] != "match":
                    self.stdout.write(json.dumps(row))
            self.stdout.write("Read-only audit: " + json.dumps(summary))
