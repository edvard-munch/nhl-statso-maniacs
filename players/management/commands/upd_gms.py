import re
from html import unescape
from datetime import datetime
from time import sleep

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from players.models import Game, Gameday, Goalie, Side, Skater, Team
from zoneinfo import ZoneInfo
from players import nhl_http
import logging

logger = logging.getLogger(__name__)

ZERO_TOI = "00:00"
DATE_REGEX = r"^(\d{4})\-(\d{2})\-(\d{2})"
WHITESPACE_REGEX = r"\s+"
HTML_TABLE_REGEX = r"<table[^>]*>(.*?)</table>"
HTML_ROW_REGEX = r"<tr[^>]*>(.*?)</tr>"
HTML_CELL_REGEX = r"<t[dh][^>]*>(.*?)</t[dh]>"
HTML_TAG_REGEX = r"<[^>]+>"
HEADER_NORMALIZE_REGEX = r"[^a-z0-9#]"
INT_REGEX = r"-?\d+"
TIME_MM_SS_REGEX = r"^\d{1,2}:\d{2}$"
# Require a surname/given-name heading (with an optional position before the
# surname). OT shift rows start with a shift number followed by "OT", not a name.
# Unicode letters also preserve headings such as "10 BÄCK, OSKAR".
PLAYER_HEADING_REGEX = r"^(\d+)\s+[^\W\d_][^,\d]*,\s*[^\W\d_][^,\d]*$"
TOTAL_ROW_LABEL = "TOT"
FACEOFF_TOTAL_VALUE_REGEX = r"^(\d+)\s*-"

# get winning goalie
URL_SCHEDULE = "https://api-web.nhle.com/v1/schedule/{}"
URL_BOXSCORE = "https://api-web.nhle.com/v1/gamecenter/{}/boxscore"
URL_RIGHT_RAIL = "https://api-web.nhle.com/v1/gamecenter/{}/right-rail"
URL_PLAY_BY_PLAY = "https://api-web.nhle.com/v1/gamecenter/{}/play-by-play"
REGULAR_SEASON_CODE = "02"
REGULAR_PERIODS_AMOUNT = 3
REPORT_FETCH_TIMEOUT = 10
JSON_FETCH_TIMEOUT = 10
JSON_FETCH_ATTEMPTS = nhl_http.ATTEMPTS
JSON_RETRY_DELAY = nhl_http.BACKOFF_SECONDS
SCHEDULE_FIELDS = {"gameWeek", "regularSeasonStartDate", "regularSeasonEndDate"}
BOXSCORE_FIELDS = {"gameState", "awayTeam", "homeTeam"}
ROSTER_SIDES = ("awayTeam", "homeTeam")
ROSTER_GROUP_POSITIONS = {
    "forwards": {"C", "L", "R", "LW", "RW"},
    "defense": {"D"},
    "goalies": {"G"},
}
GAME_ID_FIELD = "gameId"
ROSTER_RELATIONS = (
    (Skater, ("away_defencemen", "away_forwards", "home_defencemen", "home_forwards")),
    (Goalie, ("away_goalies", "home_goalies")),
)

GAME_REPORT_LINK_KEYS = ["eventSummary", "faceoffSummary", "toiAway", "toiHome"]
REPORT_STAT_KEYS = [
    "faceoffs",
    "powerPlayPoints",
    "shPoints",
    "powerPlayToi",
    "shorthandedToi",
]
STAT_DEFAULTS = {
    "faceoffs": 0,
    "powerPlayPoints": 0,
    "shPoints": 0,
    "powerPlayToi": ZERO_TOI,
    "shorthandedToi": ZERO_TOI,
}
GOAL_EVENT_TYPE = "goal"
POWER_PLAY_POINTS_KEY = "powerPlayPoints"
SHORTHANDED_POINTS_KEY = "shPoints"

GAME_STATES = {
    "scheduled": "FUT",
    "critical": "CRIT",
    "pregame": "PRE",
    "live": "LIVE",
    "softFinal": "OVER",
    "hard_final": "FINAL",
    "finished": "OFF",
}
GAME_LIVE_SUFFIX = f" ({GAME_STATES['live'].capitalize()})"
FINAL_GAME_STATES = {GAME_STATES["hard_final"], GAME_STATES["finished"]}
ACTIVE_GAME_STATES = {GAME_STATES["live"], GAME_STATES["critical"]}
PREGAME_STATES = {GAME_STATES["scheduled"], GAME_STATES["pregame"]}
STARTED_GAME_STATES = ACTIVE_GAME_STATES | FINAL_GAME_STATES | {GAME_STATES["softFinal"]}
TARGET_STARTED = "started"
TARGET_STATES = {
    TARGET_STARTED: STARTED_GAME_STATES,
    "active": ACTIVE_GAME_STATES,
    "final": FINAL_GAME_STATES,
}
SCHEDULE_OK = "OK"
SECONDS_PER_MINUTE = 60
REGULAR_GAME_ID_REGEX = r"^\d{4}02\d{4}$"
DATE_FORMAT = "%Y-%m-%d"

SIDES = {
    "away": "away",
    "home": "home",
}
MONTHS_MAP = {
    "Jan": 6,
    "Feb": 7,
    "Mar": 8,
    "Apr": 9,
    "May": 10,
    "Jun": 11,
    "Jul": 12,
    "Aug": 1,
    "Sep": 2,
    "Oct": 3,
    "Nov": 4,
    "Dec": 5,
}
MONTHS_ORDER = ["09", "10", "11", "12", "01", "02", "03", "04", "05", "06", "07", "08"]
TIMEZONE = "US/Pacific"


class Command(BaseCommand):
    def add_arguments(self, parser):
        targets = parser.add_mutually_exclusive_group()
        targets.add_argument(
            "--date",
            action="append",
            dest="dates",
            help="NHL schedule date YYYY-MM-DD; repeat for multiple dates",
        )
        targets.add_argument(
            "--game-id",
            action="append",
            dest="game_ids",
            help="Regular-season NHL game ID; repeat for multiple games",
        )
        parser.add_argument(
            "--state",
            choices=tuple(TARGET_STATES),
            help="Targeted runs only: started (default), active, or final",
        )

    def handle(self, *args, **options):
        dates = list(
            dict.fromkeys(parse_target_date(value) for value in (options.get("dates") or []))
        )
        game_ids = list(
            dict.fromkeys(parse_target_game_id(value) for value in (options.get("game_ids") or []))
        )
        if dates and game_ids:
            raise CommandError("Use --date or --game-id, not both")
        state = options.get("state")
        if state is not None and state not in TARGET_STATES:
            raise CommandError("Invalid --state; use started, active, or final")
        if state and not (dates or game_ids):
            raise CommandError("--state requires --date or --game-id")
        if dates or game_ids:
            with requests.Session() as session:
                refresh_targets(dates, game_ids, state or TARGET_STARTED, session, self.stdout)
            return
        with requests.Session() as session:
            today = datetime.now(ZoneInfo(TIMEZONE)).date()
            schedule = get_schedule(today, session)
            regular_season_end_date = datetime_from_string(schedule["regularSeasonEndDate"])
            regular_season_start_date = datetime_from_string(schedule["regularSeasonStartDate"])

            first_unfinished_gameday_in_db = (
                Gameday.objects.filter(all_games_finished=False).order_by("day").first()
            )

            first_notloaded_gameday_in_db = (
                Gameday.objects.filter(all_games_uploaded=False).order_by("day").first()
            )

            if first_unfinished_gameday_in_db:
                check_for_games(first_unfinished_gameday_in_db.day, today, session)

            if first_notloaded_gameday_in_db:
                check_for_games(first_notloaded_gameday_in_db.day, regular_season_end_date, session)

            elif not first_unfinished_gameday_in_db:
                check_for_games(regular_season_start_date, regular_season_end_date, session)


def parse_target_date(value):
    try:
        parsed = datetime.strptime(str(value), DATE_FORMAT).date()
        if parsed.isoformat() != str(value):
            raise ValueError
        return parsed
    except (ValueError, TypeError) as error:
        raise CommandError(f"Invalid target date {value!r}; use YYYY-MM-DD") from error


def parse_target_game_id(value):
    if not re.fullmatch(REGULAR_GAME_ID_REGEX, str(value), flags=re.ASCII):
        raise CommandError(f"Invalid regular-season game ID {value!r}; expected YYYY02NNNN")
    return int(value)


def target_state(payload):
    state = payload.get("gameState")
    if not isinstance(state, str) or state not in STARTED_GAME_STATES | PREGAME_STATES:
        raise CommandError(f"Invalid targeted game state {state!r}")
    return state


def scheduled_targets(date, session):
    """Use only the requested NHL date, never the surrounding week or next page."""
    schedule = fetch_json(
        URL_SCHEDULE.format(date), f"target schedule {date}", session, {"gameWeek"}
    )
    week = schedule["gameWeek"]
    if not isinstance(week, list) or any(not isinstance(day, dict) for day in week):
        raise CommandError(f"Invalid gameWeek for {date}")
    days = [day for day in week if day.get("date") == date.isoformat()]
    if len(days) != 1 or not isinstance(days[0].get("games"), list):
        raise CommandError(f"Schedule must contain exactly one games list for {date}")
    games = days[0]["games"]
    ids = []
    for game in games:
        if not isinstance(game, dict) or type(game.get("id")) is not int:
            raise CommandError(f"Invalid scheduled game identity for {date}")
        ids.append(game["id"])
        if regular_season_game(game):
            parse_target_game_id(game["id"])
            target_state(game)
    if len(ids) != len(set(ids)):
        raise CommandError(f"Duplicate scheduled game ID for {date}")
    return games


def refresh_targets(dates, game_ids, state, session, output):
    refreshed = deferred = 0
    # Dates and IDs are explicitly finite. No automatic historical/future scan.
    for date in dates:
        games = scheduled_targets(date, session)
        output.write(f"Target date {date}: {len(games)} scheduled game(s)")
        for game in games:
            game_id = game["id"]
            if not regular_season_game(game):
                output.write(f"Game {game_id}: skipped (not regular season)")
                continue
            if (
                target_state(game) not in TARGET_STATES[state]
                or game.get("gameScheduleState", SCHEDULE_OK) != SCHEDULE_OK
            ):
                deferred += 1
                output.write(
                    f"Game {game_id}: deferred (schedule state {game['gameState']}, {game.get('gameScheduleState', 'OK')})"
                )
                continue
            if refresh_target_game(game_id, session, state, date):
                refreshed += 1
                output.write(f"Game {game_id}: refreshed")
            else:
                deferred += 1
                output.write(f"Game {game_id}: deferred (boxscore outside selected states)")
        reconcile_target_day(date, games, state)
    for game_id in game_ids:
        if refresh_target_game(game_id, session, state):
            refreshed += 1
            output.write(f"Game {game_id}: refreshed")
        else:
            deferred += 1
            output.write(f"Game {game_id}: deferred (boxscore outside selected states)")
    output.write(f"Targeted refresh complete: {refreshed} refreshed, {deferred} deferred")


def refresh_target_game(game_id, session, state, date=None):
    payload = fetch_json(
        URL_BOXSCORE.format(game_id),
        f"target game {game_id}",
        session,
        {"id", "gameDate", "gameState"},
    )
    if type(payload.get("id")) is not int or payload["id"] != game_id:
        raise CommandError(f"Boxscore identity does not match requested game {game_id}")
    payload_date = parse_target_date(payload.get("gameDate"))
    if date is not None and payload_date != date:
        raise CommandError(
            f"Game {game_id}: boxscore date {payload_date} disagrees with schedule {date}"
        )
    if (
        target_state(payload) not in TARGET_STATES[state]
        or payload.get("gameScheduleState", SCHEDULE_OK) != SCHEDULE_OK
    ):
        return False
    team_ids = []
    for side in ROSTER_SIDES:
        team = payload.get(side)
        if not isinstance(team, dict) or type(team.get("id")) is not int or team["id"] <= 0:
            raise CommandError(f"Game {game_id}: {side} requires a positive team ID")
        team_ids.append(team["id"])
    if len(set(team_ids)) != len(ROSTER_SIDES):
        raise CommandError(f"Game {game_id}: home and away team IDs must differ")
    # Fetch and validate before the per-game publication transaction.
    roster = get_rosters_api(payload, game_id)
    if not roster:
        raise CommandError(f"Game {game_id}: started game is missing roster data")
    reports = get_game_report_player_stats(game_id, game_data=payload, session=session)
    publish_target_game(payload_date, payload, reports, session)
    return True


@transaction.atomic
def publish_target_game(date, payload, reports, session):
    game_id = payload["id"]
    existing = Game.objects.select_related("gameday").filter(nhl_id=game_id).first()
    if existing and (not existing.gameday or existing.gameday.day != date):
        raise CommandError(
            f"Game {game_id}: saved date differs; explicit history reconciliation required"
        )
    day = {"date": date.isoformat(), "games": [{"id": game_id}]}
    try:
        _process_games(day, session, payloads={game_id: payload}, reports={game_id: reports})
    except (Team.DoesNotExist, CommandError) as error:
        raise CommandError(f"Game {game_id} on {date}: {error}") from error


@transaction.atomic
def reconcile_target_day(date, scheduled, state):
    # Only a full started-state date refresh can promote day flags. An ID or
    # state-filtered subset must never claim it knows the whole day's coverage.
    day = Gameday.objects.filter(day=date).first()
    if not day:
        return
    expected = {game["id"] for game in scheduled}
    stored = dict(day.games.values_list("nhl_id", "game_finished"))
    complete = bool(expected) and set(stored) == expected
    finished = (
        complete
        and all(stored.values())
        and all(
            game.get("gameState") in FINAL_GAME_STATES
            and game.get("gameScheduleState", SCHEDULE_OK) == SCHEDULE_OK
            for game in scheduled
        )
    )
    if state == TARGET_STARTED:
        day.all_games_uploaded = complete
        day.all_games_finished = finished
    else:
        day.all_games_uploaded = day.all_games_uploaded and complete
        day.all_games_finished = day.all_games_finished and finished
    day.save(update_fields=["all_games_uploaded", "all_games_finished"])


def check_for_games(date, date_end, session):
    while date <= date_end:
        schedule = get_schedule(date, session)

        for weekday in schedule["gameWeek"]:
            date = datetime_from_string(weekday["date"])

            if date > date_end:
                return

            if weekday["games"]:
                print(f"{weekday['date']} games loading")
                process_games(weekday, session)

        next_start_date = schedule.get("nextStartDate")
        if next_start_date:
            date = datetime_from_string(next_start_date)
        else:
            print("Season is over")
            return


def datetime_from_string(date_string):
    return datetime.strptime(date_string, "%Y-%m-%d").date()


def regular_season_game(game):
    return str(game["id"])[4:6] == REGULAR_SEASON_CODE


def get_score(game_data):
    if game_data["gameState"] not in [GAME_STATES["scheduled"], GAME_STATES["pregame"]]:
        away_score = game_data.get("awayTeam", {}).get("score")
        home_score = game_data.get("homeTeam", {}).get("score")

        if away_score is None or home_score is None:
            away_score = (
                game_data.get("boxscore", {}).get("linescore", {}).get("totals", {}).get("away")
            )
            home_score = (
                game_data.get("boxscore", {}).get("linescore", {}).get("totals", {}).get("home")
            )

        if away_score is None or home_score is None:
            return ""

        score = f"{away_score}:{home_score}"

        if game_data["gameState"] == GAME_STATES["live"]:
            score += GAME_LIVE_SUFFIX

        period_number = game_data.get("periodDescriptor", {}).get("number", 0)
        if period_number > REGULAR_PERIODS_AMOUNT:
            if game_data["gameState"] == GAME_STATES["finished"]:
                score += f" {game_data['gameOutcome']['lastPeriodType']}"
    else:
        score = ""

    return score


@transaction.atomic
def process_games(day, session):
    """A failed required response must not publish a partially refreshed day."""
    try:
        return _process_games(day, session)
    except CommandError as error:
        raise CommandError("Gameday {}: {}".format(day["date"], error)) from error


def _process_games(day, session, *, payloads=None, reports=None):
    date_api = datetime_from_string(day["date"])
    gameday_obj = Gameday.objects.update_or_create(day=date_api)[0]
    games_finished_total = 0

    for game in day["games"]:
        game_finished = False
        if regular_season_game(game):
            game_data = (
                payloads[game["id"]]
                if payloads is not None
                else get_game_data(game["id"], URL_BOXSCORE, session)
            )
            rosters_api = None
            if game_data["gameState"] not in [GAME_STATES["scheduled"], GAME_STATES["pregame"]]:
                rosters_api = get_rosters_api(game_data, game["id"])

            team_objects = [
                Team.objects.get(nhl_id=game_data["awayTeam"]["id"]),
                Team.objects.get(nhl_id=game_data["homeTeam"]["id"]),
            ]

            team_names = [item.name for item in team_objects]

            defaults = {
                "result": f"{' - '.join(team_names)} {get_score(game_data)}",
                "gameday": gameday_obj,
                "game_finished": game_finished,
            }

            game_obj, created = Game.objects.update_or_create(nhl_id=game["id"], defaults=defaults)

            if created:
                game_obj.slug = slugify(" - ".join(team_names) + str(game_obj.gameday.day))
                game_obj.save(update_fields=["slug"])

            if game_data["gameState"] not in [GAME_STATES["scheduled"], GAME_STATES["pregame"]]:
                report_player_stats = (
                    reports[game["id"]]
                    if reports is not None
                    else get_game_report_player_stats(
                        game["id"], game_data=game_data, session=session
                    )
                )
                if rosters_api:
                    if not created:
                        remove_departed_gamelogs(game_obj, rosters_api)
                    rosters_database = prepare_rosters_for_database(
                        rosters_api,
                        team_objects,
                        gameday_obj,
                        report_player_stats,
                        game_id=game_obj.nhl_id,
                        preserve_game=game_obj if payloads is not None else None,
                    )

                    if game_data["gameState"] in FINAL_GAME_STATES and rosters_equal(
                        rosters_api, rosters_database
                    ):
                        games_finished_total += 1
                        game_obj.game_finished = True
                        game_obj.save(update_fields=["game_finished"])

                    save_rosters_to_database(rosters_database, game_obj)
                else:
                    logger.warning("Roster data missing for game %s", game["id"])

            save_game_side(team_objects[0], SIDES["away"], game_obj, day["date"])
            save_game_side(team_objects[1], SIDES["home"], game_obj, day["date"])

    if payloads is not None:
        if games_finished_total != len(day["games"]):
            gameday_obj.all_games_finished = False
            gameday_obj.save(update_fields=["all_games_finished"])
        return

    games_db = len(gameday_obj.games.all())
    games_api = len(day["games"])

    # A successful refresh can also discover that a previously complete day is
    # incomplete. Flags must describe this response, not remain sticky once true.
    gameday_obj.all_games_uploaded = (games_api > 0) and (games_db == games_api)
    gameday_obj.all_games_finished = (games_api > 0) and (games_finished_total == games_api)
    gameday_obj.save(update_fields=["all_games_uploaded", "all_games_finished"])


def get_rosters_api(game_data, game_id=None):
    """Validate a supplied roster before reports, filtering or database writes."""
    game_id = game_id if game_id is not None else game_data.get("id")

    def invalid(path, reason):
        raise CommandError(
            "Invalid roster for game {} at {}: {} {}".format(
                game_id, URL_BOXSCORE.format(game_id), path, reason
            )
        )

    rosters_api = game_data.get("playerByGameStats")
    if rosters_api is None or rosters_api == {}:
        boxscore = game_data.get("boxscore")
        if boxscore is not None:
            if not isinstance(boxscore, dict):
                invalid("boxscore", "must be an object")
            rosters_api = boxscore.get("playerByGameStats")
    if rosters_api is None or rosters_api == {}:
        return None
    if not isinstance(rosters_api, dict):
        invalid("playerByGameStats", "must be an object")
    seen = set()
    for side in ROSTER_SIDES:
        groups = rosters_api.get(side)
        path = "playerByGameStats." + side
        if not isinstance(groups, dict) or set(groups) != set(ROSTER_GROUP_POSITIONS):
            invalid(path, "must contain forwards, defense and goalies lists only")
        for group, positions in ROSTER_GROUP_POSITIONS.items():
            players = groups[group]
            if not isinstance(players, list):
                invalid(path + "." + group, "must be a list")
            for index, player in enumerate(players):
                entry = "{}.{}[{}]".format(path, group, index)
                if not isinstance(player, dict):
                    invalid(entry, "must be an object")
                player_id = normalize_report_identifier(player.get("playerId"))
                if player_id is None or player_id <= 0:
                    invalid(entry, "requires a positive playerId")
                if player_id in seen:
                    invalid(entry, "duplicates playerId {}".format(player_id))
                seen.add(player_id)
                position = player.get("position")
                if not isinstance(position, str) or position not in positions:
                    invalid(entry, "has a missing or incompatible position")
                if group == "goalies":
                    toi = player.get("toi")
                    if not isinstance(toi, str) or not re.fullmatch(TIME_MM_SS_REGEX, toi):
                        invalid(entry, "requires goalie toi in MM:SS format")
                    if toi != ZERO_TOI and "goalsAgainst" not in player:
                        invalid(entry, "requires goalsAgainst for a played goalie")
        if not any(groups.values()):
            invalid(path, "must not contain only empty groups")
    return {
        side: dict(rosters_api[side], goalies=get_played_goalies(rosters_api[side]["goalies"]))
        for side in ROSTER_SIDES
    }


def prepare_rosters_for_database(
    rosters_api,
    team_objects,
    gameday_object,
    report_player_stats=None,
    game_id=None,
    preserve_game=None,
):
    away_goalies_count = len(rosters_api["awayTeam"]["goalies"])
    home_goalies_count = len(rosters_api["homeTeam"]["goalies"])
    away_skaters = [[], []]
    away_goalies = []
    home_skaters = [[], []]
    home_goalies = []

    away_team = team_objects[0]
    home_team = team_objects[1]

    iterate_players(
        gameday_object,
        rosters_api["awayTeam"],
        away_skaters,
        away_goalies,
        away_team,
        home_team,
        away_goalies_count,
        report_player_stats,
        game_id,
        preserve_game,
    )
    iterate_players(
        gameday_object,
        rosters_api["homeTeam"],
        home_skaters,
        home_goalies,
        home_team,
        away_team,
        home_goalies_count,
        report_player_stats,
        game_id,
        preserve_game,
    )

    rosters_database = {
        "away_team": [away_skaters, away_goalies],
        "home_team": [home_skaters, home_goalies],
    }

    return rosters_database


def remove_departed_gamelogs(game, rosters):
    """Delete only verified appearances of participants absent from this refresh."""
    current_ids = {
        normalize_report_identifier(player["playerId"])
        for side in rosters.values()
        for players in side.values()
        for player in players
    }
    day = str(game.gameday.day)
    team_abbrs = set(game.teams.values_list("abbr", flat=True))
    for model, fields in ROSTER_RELATIONS:
        departed = {}
        for field in fields:
            for player in getattr(game, field).exclude(nhl_id__in=current_ids):
                departed[player.pk] = player
        for player in departed.values():
            logs = player.gamelog_stats
            if not isinstance(logs, dict) or day not in logs:
                continue
            if not gamelog_belongs_to_game(logs[day], player, game, fields, team_abbrs):
                logger.warning(
                    "Retaining unverified gamelog for %s %s on %s when removing from game %s",
                    model.__name__,
                    player.nhl_id,
                    day,
                    game.nhl_id,
                )
                continue
            logs = dict(logs)
            del logs[day]
            player.gamelog_stats = logs
            player.save(update_fields=["gamelog_stats"])


def gamelog_belongs_to_game(entry, player, game, fields, team_abbrs):
    if not isinstance(entry, dict):
        return False
    identity = entry.get("player")
    if (
        not isinstance(identity, dict)
        or normalize_report_identifier(identity.get("nhl_id")) != player.nhl_id
    ):
        return False
    if GAME_ID_FIELD in entry:
        return normalize_report_identifier(entry[GAME_ID_FIELD]) == game.nhl_id
    team = entry.get("team")
    opponent = entry.get("opponent")
    if not all(
        isinstance(value, dict) and isinstance(value.get("abbr"), str) for value in (team, opponent)
    ):
        return False
    if (
        len(team_abbrs) != len(ROSTER_SIDES)
        or {team.get("abbr"), opponent.get("abbr")} != team_abbrs
    ):
        return False
    appearances = Q()
    for field in fields:
        appearances |= Q(**{field: player.pk})
    return (
        not Game.objects.filter(gameday=game.gameday)
        .exclude(pk=game.pk)
        .filter(appearances)
        .exists()
    )


def save_rosters_to_database(rosters, game_object):
    game_object.away_defencemen.set(rosters["away_team"][0][0])
    game_object.away_forwards.set(rosters["away_team"][0][1])
    game_object.away_goalies.set(rosters["away_team"][1])

    game_object.home_defencemen.set(rosters["home_team"][0][0])
    game_object.home_forwards.set(rosters["home_team"][0][1])
    game_object.home_goalies.set(rosters["home_team"][1])


def rosters_equal(rosters_api, rosters_database):
    roster_home_team_db_length = (
        len(rosters_database["home_team"][0][0])
        + len(rosters_database["home_team"][0][1])
        + len(rosters_database["home_team"][1])
    )

    roster_home_team_api_length = (
        len(rosters_api["homeTeam"]["forwards"])
        + len(rosters_api["homeTeam"]["defense"])
        + len(rosters_api["homeTeam"]["goalies"])
    )

    roster_away_team_db_length = (
        len(rosters_database["away_team"][0][0])
        + len(rosters_database["away_team"][0][1])
        + len(rosters_database["away_team"][1])
    )

    roster_away_team_api_length = (
        len(rosters_api["awayTeam"]["forwards"])
        + len(rosters_api["awayTeam"]["defense"])
        + len(rosters_api["awayTeam"]["goalies"])
    )

    return (roster_home_team_db_length == roster_home_team_api_length) and (
        roster_away_team_db_length == roster_away_team_api_length
    )


def get_played_goalies(goalies):
    return [goalie for goalie in goalies if goalie.get("toi", ZERO_TOI) != ZERO_TOI]


def get_schedule(date, session=None):
    return fetch_json(
        URL_SCHEDULE.format(date), "schedule for {}".format(date), session, SCHEDULE_FIELDS
    )


def iterate_players(
    gameday_obj,
    roster,
    skaters_list,
    goalies_list,
    team,
    opponent,
    goalies_count,
    report_player_stats=None,
    game_id=None,
    preserve_game=None,
):
    for _, value in roster.items():
        for player_data in value:
            player = get_player(player_data["playerId"])

            if player:
                unknown_fields = []
                if preserve_game is not None:
                    unknown_fields = preserve_target_report_stats(
                        player_data, player, preserve_game, report_player_stats
                    )
                game_stats = add_player(
                    player_data,
                    player,
                    skaters_list,
                    goalies_list,
                    team,
                    opponent,
                    goalies_count,
                    report_player_stats,
                )
                format_date = date_convert(gameday_obj.day)

                # chek if not 'Scratched'
                if game_stats:
                    # Broad refresh defaults remain compatible. Targeted unknowns
                    # must not become fabricated zero special-team statistics.
                    for field in unknown_fields:
                        game_stats[field] = None
                    game_stats["format_date"] = format_date
                    if game_id is not None:
                        game_stats[GAME_ID_FIELD] = game_id
                    player.gamelog_stats[str(gameday_obj.day)] = game_stats
                    player.save(update_fields=["gamelog_stats"])
            else:
                print(player_data)
                logger.warning(
                    f"{player_data['name']['default']} from {team} not found and will not be added to the game"
                )


def valid_saved_report_value(field, value):
    if field in {"powerPlayToi", "shorthandedToi"}:
        return (
            isinstance(value, str)
            and bool(re.fullmatch(TIME_MM_SS_REGEX, value))
            and int(value.split(":")[1]) < SECONDS_PER_MINUTE
        )
    return type(value) is int and value >= 0


def preserve_target_report_stats(player_data, player, game, reports):
    """Fresh boxscore/report values (including zero) win; retain known same-game values."""
    hydrate_player_stats_from_reports(player_data, reports)
    logs = player.gamelog_stats
    previous = logs.get(str(game.gameday.day)) if isinstance(logs, dict) else None
    if previous is not None:
        fields = next(fields for model, fields in ROSTER_RELATIONS if isinstance(player, model))
        teams = set(game.teams.values_list("abbr", flat=True))
        if not gamelog_belongs_to_game(previous, player, game, fields, teams):
            raise CommandError(
                f"Unverified same-date gamelog for player {player.nhl_id}; refusing to overwrite"
            )
    unknown = []
    for field in REPORT_STAT_KEYS:
        if player_data.get(field) in (None, ""):
            old = previous.get(field) if previous else None
            if valid_saved_report_value(field, old):
                player_data[field] = old
            else:
                unknown.append(field)
    return unknown


def date_convert(date):
    date_str = date.strftime("%b %e")
    return re.sub(WHITESPACE_REGEX, " ", date_str)


def add_player(
    player_data,
    player,
    skaters_list,
    goalies_list,
    team,
    opponent,
    goalies_count,
    report_player_stats=None,
):
    hydrate_player_stats_from_reports(player_data, report_player_stats)
    normalize_player_game_stats(player_data)

    if player_data["position"] == "G":
        if player_data["goalsAgainst"] == 0 and goalies_count == 1:
            player_data["shutout"] = 1
        else:
            player_data["shutout"] = 0

        add_values(player_data, team, opponent, player)

        goalies_list.append(player)

    elif player_data["position"] == "D":
        add_values(player_data, team, opponent, player)
        skaters_list[0].append(player)
    else:
        add_values(player_data, team, opponent, player)
        skaters_list[1].append(player)

    return player_data


def normalize_player_game_stats(player_data):
    for stat_key, default_value in STAT_DEFAULTS.items():
        if player_data.get(stat_key) in [None, ""]:
            player_data[stat_key] = default_value


def hydrate_player_stats_from_reports(player_data, report_player_stats):
    if not report_player_stats:
        return

    player_id = normalize_report_identifier(player_data.get("playerId"))
    report_stats = report_player_stats.get(player_id)

    if not report_stats:
        return

    for stat_key in REPORT_STAT_KEYS:
        report_value = report_stats.get(stat_key)
        if report_value in [None, ""]:
            continue

        if player_data.get(stat_key) in [None, ""]:
            player_data[stat_key] = report_value


def add_values(game_stats, team, opponent, player):
    game_stats["player"] = {}
    game_stats["player"]["nhl_id"] = player.nhl_id
    game_stats["player"]["slug"] = player.slug
    game_stats["player"]["name"] = player.name
    game_stats["team"] = {}
    game_stats["team"]["name"] = team.name
    game_stats["team"]["abbr"] = team.abbr
    game_stats["opponent"] = {}
    game_stats["opponent"]["name"] = opponent.name
    game_stats["opponent"]["abbr"] = opponent.abbr


def save_game_side(team, side, game, date):
    defaults = {
        "team": team,
        "side": side,
        "game": game,
    }

    Side.objects.update_or_create(nhl_side_id=get_gameside_id(date, team), defaults=defaults)


def get_gameside_id(date, team):
    matches = re.search(DATE_REGEX, date)
    date_id = matches[1] + matches[2] + matches[3]
    side_id = str(team.nhl_id)
    return int(date_id + side_id)


def get_player(nhl_id):
    """
    Fetches object of Skater or Goalie models

    If object is not found in either of models it returns `None`

    Args:
        nhl_id: integer representing a player's id from nhl.com API
    """
    try:
        return Skater.objects.select_related("team").get(nhl_id=nhl_id)
    except Skater.DoesNotExist:
        try:
            return Goalie.objects.select_related("team").get(nhl_id=nhl_id)
        except Goalie.DoesNotExist:
            return None


def get_game_data(game_id, url, session=None):
    required = BOXSCORE_FIELDS if url == URL_BOXSCORE else ()
    return fetch_json(url.format(game_id), "game {}".format(game_id), session, required)


def fetch_json(url, context, session=None, required_fields=()):
    """Bounded retries; an unavailable endpoint must never resemble empty stats."""

    def checked_json(response):
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        if not set(required_fields).issubset(payload):
            raise ValueError(
                "Missing required fields: {}".format(
                    ", ".join(sorted(set(required_fields) - set(payload)))
                )
            )
        return payload

    return nhl_http.required_get(
        url,
        session=session,
        context=context,
        timeout=JSON_FETCH_TIMEOUT,
        attempts=JSON_FETCH_ATTEMPTS,
        validate=checked_json,
        sleep_fn=sleep,
    )


def get_game_report_links(game_id, session=None):
    right_rail_data = get_game_data(game_id, URL_RIGHT_RAIL, session)
    return extract_game_report_links(right_rail_data)


def extract_game_report_links(right_rail_data):
    links = {key: None for key in GAME_REPORT_LINK_KEYS}
    reports = right_rail_data.get("gameReports") if isinstance(right_rail_data, dict) else None

    if not isinstance(reports, dict):
        return links

    for key in GAME_REPORT_LINK_KEYS:
        report_url = reports.get(key)
        if is_valid_report_url(report_url):
            links[key] = report_url

    return links


def is_valid_report_url(report_url):
    return isinstance(report_url, str) and report_url.startswith(("http://", "https://"))


def fetch_report_html(report_url, session=None):
    if not is_valid_report_url(report_url):
        return None

    response = nhl_http.optional_get(
        report_url, session=session, timeout=REPORT_FETCH_TIMEOUT, context="HTML game report"
    )
    if response is None:
        return None

    return response.text


def get_game_report_player_stats(game_id, game_data=None, session=None):
    """Resolve report rows to player IDs before combining any statistics."""
    links = get_game_report_links(game_id, session)
    report_stats = {}
    all_players = map_report_sweaters_to_players(game_data)
    for key, parser in (
        ("eventSummary", parse_event_summary_report),
        ("faceoffSummary", parse_faceoff_summary_report),
    ):
        html = fetch_report_html(links.get(key), session)
        merge_player_report_stats(
            report_stats,
            resolve_report_players(
                parser(html), all_players, "{} for game {}".format(key, game_id)
            ),
        )
    for key, side in (("toiAway", "awayTeam"), ("toiHome", "homeTeam")):
        html = fetch_report_html(links.get(key), session)
        scoped_players = map_report_sweaters_to_players(game_data, side)
        merge_player_report_stats(
            report_stats,
            resolve_report_players(
                parse_toi_report(html), scoped_players, "{} for game {}".format(key, game_id)
            ),
        )
    play_by_play_data = get_game_data(game_id, URL_PLAY_BY_PLAY, session)
    known_ids = {
        normalize_report_identifier(player.get("playerId"))
        for player in report_roster_players(game_data)
    } - {None}
    merge_player_report_stats(
        report_stats,
        filter_special_teams_points(parse_special_teams_points(play_by_play_data), known_ids),
    )
    return report_stats


def merge_player_report_stats(base_stats, stats_to_merge):
    for player_id, report_stats in stats_to_merge.items():
        base_stats.setdefault(player_id, {})
        base_stats[player_id].update(report_stats)


def normalize_report_identifier(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def report_roster_players(game_data, side=None):
    data = game_data or {}
    rosters = data.get("playerByGameStats")
    if not rosters:
        boxscore = data.get("boxscore") or {}
        rosters = boxscore.get("playerByGameStats") if isinstance(boxscore, dict) else None
    if not isinstance(rosters, dict):
        return
    for team_side in (side,) if side else ("awayTeam", "homeTeam"):
        groups = rosters.get(team_side)
        if not isinstance(groups, dict):
            continue
        for group, players in groups.items():
            if not isinstance(players, list):
                continue
            for player in players:
                if not isinstance(player, dict):
                    continue
                if group == "goalies" and player.get("toi", ZERO_TOI) == ZERO_TOI:
                    continue
                yield player


def map_report_sweaters_to_players(game_data, side=None):
    players = {}
    for player in report_roster_players(game_data, side):
        player_id = normalize_report_identifier(player.get("playerId"))
        sweater = normalize_report_identifier(player.get("sweaterNumber"))
        if player_id is not None and sweater is not None:
            players.setdefault(sweater, set()).add(player_id)
    return players


def resolve_report_players(stats_by_sweater, roster, label):
    resolved = {}
    for sweater, stats in stats_by_sweater.items():
        candidates = roster.get(normalize_report_identifier(sweater), set())
        if len(candidates) == 1:
            resolved[next(iter(candidates))] = stats
        elif candidates:
            logger.warning("Ignoring %s stats for ambiguous sweater %s", label, sweater)
    return resolved


def parse_special_teams_points(play_by_play_data):
    away_team_id = (play_by_play_data or {}).get("awayTeam", {}).get("id")
    home_team_id = (play_by_play_data or {}).get("homeTeam", {}).get("id")
    points = {}

    for play in (play_by_play_data or {}).get("plays", []):
        if play.get("typeDescKey") != GOAL_EVENT_TYPE:
            continue

        points_key = get_goal_points_key(play, away_team_id, home_team_id)
        if not points_key:
            continue

        details = play.get("details", {})
        for player_id in [
            details.get("scoringPlayerId"),
            details.get("assist1PlayerId"),
            details.get("assist2PlayerId"),
        ]:
            if player_id is None:
                continue

            points.setdefault(player_id, {POWER_PLAY_POINTS_KEY: 0, SHORTHANDED_POINTS_KEY: 0})
            points[player_id][points_key] += 1

    return points


def get_goal_points_key(goal_play, away_team_id, home_team_id):
    owner_team_id = goal_play.get("details", {}).get("eventOwnerTeamId")
    if owner_team_id not in [away_team_id, home_team_id]:
        return None

    skaters = parse_situation_skaters(goal_play.get("situationCode"))
    if not skaters:
        return None

    away_skaters, home_skaters = skaters
    if owner_team_id == away_team_id:
        team_skaters = away_skaters
        opponent_skaters = home_skaters
    else:
        team_skaters = home_skaters
        opponent_skaters = away_skaters

    if team_skaters > opponent_skaters:
        return POWER_PLAY_POINTS_KEY

    if team_skaters < opponent_skaters:
        return SHORTHANDED_POINTS_KEY

    return None


def parse_situation_skaters(situation_code):
    if situation_code is None:
        return None

    code = str(situation_code)
    if not code.isdigit():
        return None

    code = code.zfill(4)
    return int(code[1]), int(code[2])


def filter_special_teams_points(player_points, known_ids):
    return {
        normalize_report_identifier(player_id): {
            POWER_PLAY_POINTS_KEY: points.get(POWER_PLAY_POINTS_KEY),
            SHORTHANDED_POINTS_KEY: points.get(SHORTHANDED_POINTS_KEY),
        }
        for player_id, points in player_points.items()
        if normalize_report_identifier(player_id) in known_ids
    }


def parse_event_summary_report(report_html):
    return parse_report_table(
        report_html,
        {
            "powerPlayPoints": ["ppp", "powerplaypoints"],
            "shPoints": ["shp", "shorthandedpoints", "short-handedpoints"],
        },
        {"powerPlayPoints": parse_int_stat, "shPoints": parse_int_stat},
    )


def parse_faceoff_summary_report(report_html):
    parsed = parse_report_table(
        report_html,
        {"faceoffs": ["fow", "faceoffwins", "faceoffs"]},
        {"faceoffs": parse_int_stat},
    )
    if parsed:
        return parsed

    return parse_faceoff_summary_blocks(report_html)


def parse_toi_report(report_html):
    parsed = parse_report_table(
        report_html,
        {
            "powerPlayToi": ["toipp", "powerplaytoi", "pp"],
            "shorthandedToi": ["toish", "shorthandedtoi", "sh"],
        },
        {"powerPlayToi": parse_time_stat, "shorthandedToi": parse_time_stat},
    )
    if parsed:
        return parsed

    return parse_toi_blocks(report_html)


def parse_faceoff_summary_blocks(report_html):
    rows = parse_html_rows(report_html)
    parsed = {}
    index = 0

    while index < len(rows):
        heading_row = " ".join(rows[index])
        match = parse_player_heading_sweater(heading_row)
        if not match:
            index += 1
            continue

        sweater_number = match
        wins = None
        scan_index = index + 1
        while scan_index < len(rows):
            scan_row_text = " ".join(rows[scan_index])
            if parse_player_heading_sweater(scan_row_text):
                break

            if rows[scan_index] and rows[scan_index][0] == TOTAL_ROW_LABEL:
                total_cell = rows[scan_index][-1]
                total_match = re.match(FACEOFF_TOTAL_VALUE_REGEX, total_cell)
                if total_match:
                    wins = int(total_match.group(1))
                break

            scan_index += 1

        if wins is not None:
            parsed[sweater_number] = {"faceoffs": wins}

        index = scan_index

    return parsed


def parse_toi_blocks(report_html):
    rows = parse_html_rows(report_html)
    parsed = {}
    index = 0

    while index < len(rows):
        heading_row = " ".join(rows[index])
        match = parse_player_heading_sweater(heading_row)
        if not match:
            index += 1
            continue

        sweater_number = match
        scan_index = index + 1
        while scan_index < len(rows):
            scan_row_text = " ".join(rows[scan_index])
            if parse_player_heading_sweater(scan_row_text):
                break

            if (
                rows[scan_index]
                and rows[scan_index][0] == TOTAL_ROW_LABEL
                and len(rows[scan_index]) >= 7
            ):
                parsed[sweater_number] = {
                    "powerPlayToi": parse_time_stat(rows[scan_index][-2]),
                    "shorthandedToi": parse_time_stat(rows[scan_index][-1]),
                }
                break

            scan_index += 1

        index = scan_index

    return parsed


def parse_report_table(report_html, stat_headers, stat_parsers):
    tables_rows = parse_html_tables_rows(report_html)
    for rows in tables_rows:
        parsed = parse_report_table_rows(rows, stat_headers, stat_parsers)
        if parsed:
            return parsed

    return {}


def parse_report_table_rows(rows, stat_headers, stat_parsers):
    if len(rows) < 2:
        return {}

    for header_index, row in enumerate(rows):
        header = [normalize_header_name(cell) for cell in row]
        sweater_col = find_header_index(header, ["#", "number", "num", "jersey"])
        if sweater_col is None:
            continue

        stat_columns = {}
        for stat_key, aliases in stat_headers.items():
            stat_column = find_header_index(header, aliases)
            if stat_column is not None:
                stat_columns[stat_key] = stat_column

        if not stat_columns:
            continue

        parsed = {}
        for data_row in rows[header_index + 1 :]:
            sweater_number = parse_int_stat(get_cell_value(data_row, sweater_col))
            if sweater_number is None:
                continue

            parsed_row = {}
            for stat_key, stat_column in stat_columns.items():
                parser = stat_parsers[stat_key]
                parsed_row[stat_key] = parser(get_cell_value(data_row, stat_column))

            parsed[sweater_number] = parsed_row

        if parsed:
            return parsed

    return {}


def parse_html_tables_rows(report_html):
    if not report_html:
        return []

    tables_rows = []
    table_matches = re.findall(HTML_TABLE_REGEX, report_html, flags=re.IGNORECASE | re.DOTALL)
    for table_html in table_matches:
        rows = []
        row_matches = re.findall(HTML_ROW_REGEX, table_html, flags=re.IGNORECASE | re.DOTALL)
        for row_html in row_matches:
            cell_matches = re.findall(HTML_CELL_REGEX, row_html, flags=re.IGNORECASE | re.DOTALL)
            if cell_matches:
                rows.append([clean_html_cell(cell) for cell in cell_matches])

        if rows:
            tables_rows.append(rows)

    return tables_rows


def parse_html_rows(report_html):
    if not report_html:
        return []

    rows = []
    row_matches = re.findall(HTML_ROW_REGEX, report_html, flags=re.IGNORECASE | re.DOTALL)
    for row_html in row_matches:
        cell_matches = re.findall(HTML_CELL_REGEX, row_html, flags=re.IGNORECASE | re.DOTALL)
        if cell_matches:
            rows.append([clean_html_cell(cell) for cell in cell_matches])

    return rows


def clean_html_cell(cell_html):
    text = re.sub(HTML_TAG_REGEX, " ", cell_html)
    text = unescape(text)
    return re.sub(WHITESPACE_REGEX, " ", text).strip()


def normalize_header_name(header):
    return re.sub(HEADER_NORMALIZE_REGEX, "", header.lower())


def find_header_index(header, aliases):
    normalized_aliases = {normalize_header_name(alias) for alias in aliases}
    for index, header_name in enumerate(header):
        if header_name in normalized_aliases:
            return index

    return None


def get_cell_value(row, index):
    if index is None or index >= len(row):
        return ""

    return row[index]


def parse_int_stat(value):
    matches = re.findall(INT_REGEX, value or "")
    if not matches:
        return None

    return int(matches[0])


def parse_time_stat(value):
    value = (value or "").strip()
    if not value:
        return ""

    if re.match(TIME_MM_SS_REGEX, value):
        return value

    return ""


def parse_player_heading_sweater(row_text):
    match = re.match(PLAYER_HEADING_REGEX, row_text)
    if match and not row_text.startswith(TOTAL_ROW_LABEL):
        return int(match.group(1))

    return None
