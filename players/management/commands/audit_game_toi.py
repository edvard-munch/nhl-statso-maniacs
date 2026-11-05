"""Compare saved game PP/SH time with current NHL sources without writing data."""

from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import math
from pathlib import Path
from time import monotonic, sleep
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

REQUEST_DELAY = 1.0
RATE_LIMIT_STATUS = 429
RATE_LIMIT_ATTEMPTS = 3
RATE_BACKOFF_SECONDS = 5
MAX_RATE_WAIT_SECONDS = 60
CHECKPOINT_VERSION = 1


class AuditRateLimitError(Exception):
    """Stop this audit rather than repeatedly hitting a throttled service."""


class AuditSession(requests.Session):
    def __init__(self, delay, progress):
        super().__init__()
        self.delay = delay
        self.progress = progress
        self.last_request = None

    def get(self, url, **kwargs):
        for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
            if self.last_request is not None:
                sleep(max(0, self.delay - (monotonic() - self.last_request)))
            self.last_request = monotonic()
            response = super().get(url, **kwargs)
            if response.status_code != RATE_LIMIT_STATUS:
                return response
            retry_after = response.headers.get("Retry-After")
            response.close()
            if attempt == RATE_LIMIT_ATTEMPTS:
                raise AuditRateLimitError(f"Rate limit persists at {url}; stopping audit.")
            wait = RATE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            if retry_after:
                try:
                    requested = float(retry_after)
                except ValueError:
                    try:
                        requested = (
                            parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)
                        ).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        requested = 0
                if math.isfinite(requested):
                    wait = max(wait, requested)
            if wait > MAX_RATE_WAIT_SECONDS:
                raise AuditRateLimitError(
                    f"Server requests a {wait:.0f}s wait at {url}; stopping instead of retrying early."
                )
            self.progress(
                f"Rate limited: waiting {wait:.1f}s before retry {attempt + 1}/"
                f"{RATE_LIMIT_ATTEMPTS}: {url}"
            )
            sleep(wait)


def checkpoint_selection(options):
    return {
        key: sorted(options[key]) if key == "game_id" and options[key] else options[key]
        for key in ("season", "start_date", "end_date", "game_id", "include_unfinished")
    }


class Checkpoint:
    """Append one flushed JSON line per game; latest result wins on retry."""

    def __init__(self, path, resume, selection):
        self.file = None
        self.results = {}
        if not path:
            if resume:
                raise CommandError("--resume requires --output.")
            return
        header = dict(type="audit", version=CHECKPOINT_VERSION, selection=selection)
        try:
            if resume:
                self.file = Path(path).open("r+b")
                lines = self.file.readlines()
                if not lines or json.loads(lines[0]) != header:
                    raise ValueError("Checkpoint version/selection does not match this audit.")
                offset = len(lines[0])
                for index, line in enumerate(lines[1:], start=1):
                    if not line.endswith(b"\n") and index == len(lines) - 1:
                        # A killed write may leave only part of the last JSON line.
                        self.file.seek(offset)
                        self.file.truncate()
                        break
                    row = json.loads(line)
                    if (
                        row.get("type") != "game"
                        or not isinstance(row.get("game_id"), int)
                        or not isinstance(row.get("records"), list)
                        or not row["records"]
                        or any(
                            not isinstance(r, dict)
                            or r.get("status") not in STATUSES
                            or r.get("game_id") != row["game_id"]
                            or r.get("date") != row.get("date")
                            for r in row["records"]
                        )
                    ):
                        raise ValueError("Invalid game checkpoint record.")
                    self.results[row["game_id"]] = row
                    offset += len(line)
                self.file.seek(0, 2)
            else:
                self.file = Path(path).open("xb")
                self.write(header)
        except (OSError, ValueError, AttributeError, TypeError) as error:
            self.close()
            raise CommandError(f"Cannot use audit checkpoint: {error}") from error

    def write(self, row):
        if self.file:
            self.file.write((json.dumps(row) + "\n").encode("utf-8"))
            self.file.flush()

    def save(self, game, records):
        row = dict(
            type="game",
            game_id=game.nhl_id,
            date=str(game.gameday.day) if game.gameday else None,
            records=records,
        )
        self.write(row)
        self.results[game.nhl_id] = row

    def close(self):
        if self.file:
            self.file.close()


def summarize(results):
    records = [record for row in results.values() for record in row["records"]]
    summary = {status: sum(r["status"] == status for r in records) for status in STATUSES}
    summary["games"] = len(results)
    summary["games_with_mismatches"] = len(
        {r["game_id"] for r in records if r["status"] == "mismatch"}
    )
    summary["games_unverified"] = len(
        {r["game_id"] for r in records if r["status"] == "unverified"}
    )
    return summary, records


def toi_seconds(value):
    if not isinstance(value, str) or not re.fullmatch(upd_gms.TIME_MM_SS_REGEX, value):
        return None
    minutes, seconds = map(int, value.split(":"))
    return minutes * 60 + seconds if seconds < 60 else None


def select_games(options):
    games = Game.objects.select_related("gameday").order_by("gameday__day", "nhl_id")
    if not options["include_unfinished"]:
        games = games.filter(game_finished=True)
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

        parser.add_argument(
            "--include-unfinished",
            action="store_true",
            help="Also inspect locally unfinished games (NHL must still be final)",
        )
        parser.add_argument(
            "--request-delay",
            type=float,
            default=REQUEST_DELAY,
            help="Minimum seconds between HTTP requests (default: %(default)s)",
        )
        parser.add_argument(
            "--output", help="Incremental JSONL checkpoint; never overwrites a file"
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Resume --output; retry unverified games, skip verified games",
        )

    def handle(self, *args, **options):
        if not math.isfinite(options["request_delay"]) or options["request_delay"] < 0:
            raise CommandError("--request-delay must be finite and nonnegative.")
        games = list(select_games(options))
        checkpoint = Checkpoint(options["output"], options["resume"], checkpoint_selection(options))
        selected_days = {
            game.nhl_id: str(game.gameday.day) if game.gameday else None for game in games
        }
        checkpoint.results = {
            key: value
            for key, value in checkpoint.results.items()
            if key in selected_days and value["date"] == selected_days[key]
        }
        started = monotonic()
        stopped = None

        def progress(message):
            self.stderr.write(message)
            self.stderr.flush()

        if options["output"]:
            progress(f"Checkpoint: {Path(options['output']).resolve()}")
        else:
            progress("No checkpoint: use --output PATH to preserve progress for --resume.")
        progress(f"Selected {len(games)} saved games; database is read-only.")
        try:
            with AuditSession(options["request_delay"], progress) as session:
                for index, game in enumerate(games, start=1):
                    day = str(game.gameday.day) if game.gameday else None
                    previous = checkpoint.results.get(game.nhl_id)
                    prefix = f"[{index}/{len(games)}] {day} · game {game.nhl_id}"
                    if (
                        previous
                        and previous["date"] == day
                        and all(r["status"] != "unverified" for r in previous["records"])
                    ):
                        progress(prefix + " · already audited (checkpoint)")
                        continue
                    progress(prefix)
                    try:
                        records = audit_game(game, session)
                    except AuditRateLimitError as error:
                        stopped = str(error)
                        records = [
                            dict(game_id=game.nhl_id, date=day, status="unverified", reason=stopped)
                        ]
                    checkpoint.save(game, records)
                    summary, _ = summarize(checkpoint.results)
                    progress(
                        f"  {len(checkpoint.results)}/{len(games)} recorded · "
                        f"{summary['games_with_mismatches']} games with mismatches · "
                        f"{summary['games_unverified']} unverified · "
                        f"{monotonic() - started:.1f}s elapsed"
                    )
                    if stopped:
                        break
        except KeyboardInterrupt:
            stopped = "Interrupted; completed game results are preserved in --output if supplied."
        finally:
            checkpoint.close()
        summary, records = summarize(checkpoint.results)
        if options["json_output"]:
            self.stdout.write(json.dumps(dict(summary=summary, records=records)))
        else:
            for row in records:
                if row["status"] != "match":
                    self.stdout.write(json.dumps(row))
            self.stdout.write("Read-only audit: " + json.dumps(summary))
        progress(
            f"Audit {'stopped' if stopped else 'finished'}: {summary['games']}/{len(games)} "
            f"games recorded in {monotonic() - started:.1f}s. "
            f"Report: {options['output'] or 'stdout'}"
        )
        if stopped:
            raise CommandError(stopped)
