import re
from html import unescape
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from players.models import Game, Gameday, Goalie, Side, Skater, Team
from pytz import timezone
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

# get winning goalie
URL_SCHEDULE = "https://api-web.nhle.com/v1/schedule/{}"
URL_BOXSCORE = "https://api-web.nhle.com/v1/gamecenter/{}/boxscore"
URL_RIGHT_RAIL = "https://api-web.nhle.com/v1/gamecenter/{}/right-rail"
REGULAR_SEASON_CODE = "02"
REGULAR_PERIODS_AMOUNT = 3
REPORT_FETCH_TIMEOUT = 10

GAME_REPORT_LINK_KEYS = ["eventSummary", "faceoffSummary", "toiAway", "toiHome"]
REPORT_STAT_KEYS = [
    "faceoffs",
    "powerPlayPoints",
    "shPoints",
    "powerPlayToi",
    "shorthandedToi",
]

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
    def handle(self, *args, **options):
        with requests.Session() as session:
            today = datetime.now(timezone(TIMEZONE)).date()
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


def process_games(day, session):
    date_api = datetime_from_string(day["date"])
    gameday_obj = Gameday.objects.update_or_create(day=date_api)[0]
    games_finished_total = 0

    for game in day["games"]:
        game_finished = False
        if regular_season_game(game):
            game_data = get_game_data(game["id"], URL_BOXSCORE, session)

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
                report_player_stats = get_game_report_player_stats(game["id"], session)
                rosters_api = get_rosters_api(game_data)
                if rosters_api:
                    rosters_database = prepare_rosters_for_database(
                        rosters_api, team_objects, gameday_obj, report_player_stats
                    )

                    if rosters_equal(rosters_api, rosters_database):
                        games_finished_total += 1
                        game_obj.game_finished = True
                        game_obj.save(update_fields=["game_finished"])

                    save_rosters_to_database(rosters_database, game_obj)
                else:
                    logger.warning("Roster data missing for game %s", game["id"])

            save_game_side(team_objects[0], SIDES["away"], game_obj, day["date"])
            save_game_side(team_objects[1], SIDES["home"], game_obj, day["date"])

    games_db = len(gameday_obj.games.all())
    games_api = len(day["games"])

    if (games_api > 0) and (games_db == games_api):
        gameday_obj.all_games_uploaded = True
        gameday_obj.save(update_fields=["all_games_uploaded"])

    if (games_api > 0) and (games_finished_total == games_api):
        gameday_obj.all_games_finished = True
        gameday_obj.save(update_fields=["all_games_finished"])


def get_rosters_api(game_data):
    rosters_api = game_data.get("playerByGameStats") or game_data.get("boxscore", {}).get(
        "playerByGameStats"
    )
    if not rosters_api:
        return None

    away_team = rosters_api.get("awayTeam")
    home_team = rosters_api.get("homeTeam")
    if not away_team or not home_team:
        return None

    rosters_api["awayTeam"]["goalies"] = get_played_goalies(
        rosters_api["awayTeam"].get("goalies", [])
    )
    rosters_api["homeTeam"]["goalies"] = get_played_goalies(
        rosters_api["homeTeam"].get("goalies", [])
    )

    return rosters_api


def prepare_rosters_for_database(
    rosters_api, team_objects, gameday_object, report_player_stats=None
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
    )

    rosters_database = {
        "away_team": [away_skaters, away_goalies],
        "home_team": [home_skaters, home_goalies],
    }

    return rosters_database


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
    client = session or requests
    return client.get(URL_SCHEDULE.format(date)).json()


def iterate_players(
    gameday_obj,
    roster,
    skaters_list,
    goalies_list,
    team,
    opponent,
    goalies_count,
    report_player_stats=None,
):
    for _, value in roster.items():
        for player_data in value:
            player = get_player(player_data["playerId"])

            if player:
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
                    game_stats["format_date"] = format_date
                    player.gamelog_stats[str(gameday_obj.day)] = game_stats
                    player.save(update_fields=["gamelog_stats"])
            else:
                print(player_data)
                logger.warning(
                    f"{player_data['name']['default']} from {team} not found and will not be added to the game"
                )


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


def hydrate_player_stats_from_reports(player_data, report_player_stats):
    if not report_player_stats:
        return

    sweater_number = player_data.get("sweaterNumber")
    report_stats = report_player_stats.get(sweater_number)

    if not report_stats:
        report_stats = report_player_stats.get(str(sweater_number))

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
    client = session or requests
    return client.get(url.format(game_id)).json()


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

    client = session or requests
    try:
        response = client.get(report_url, timeout=REPORT_FETCH_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return None

    return response.text


def get_game_report_player_stats(game_id, session=None):
    links = get_game_report_links(game_id, session)
    report_stats = {}

    event_html = fetch_report_html(links.get("eventSummary"), session)
    merge_player_report_stats(report_stats, parse_event_summary_report(event_html))

    faceoff_html = fetch_report_html(links.get("faceoffSummary"), session)
    merge_player_report_stats(report_stats, parse_faceoff_summary_report(faceoff_html))

    toi_away_html = fetch_report_html(links.get("toiAway"), session)
    merge_player_report_stats(report_stats, parse_toi_report(toi_away_html))

    toi_home_html = fetch_report_html(links.get("toiHome"), session)
    merge_player_report_stats(report_stats, parse_toi_report(toi_home_html))

    return report_stats


def merge_player_report_stats(base_stats, stats_to_merge):
    for sweater_number, report_stats in stats_to_merge.items():
        base_stats.setdefault(sweater_number, {})
        base_stats[sweater_number].update(report_stats)


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
    return parse_report_table(
        report_html,
        {"faceoffs": ["fow", "faceoffwins", "faceoffs"]},
        {"faceoffs": parse_int_stat},
    )


def parse_toi_report(report_html):
    return parse_report_table(
        report_html,
        {
            "powerPlayToi": ["toipp", "powerplaytoi", "pp"],
            "shorthandedToi": ["toish", "shorthandedtoi", "sh"],
        },
        {"powerPlayToi": parse_time_stat, "shorthandedToi": parse_time_stat},
    )


def parse_report_table(report_html, stat_headers, stat_parsers):
    rows = parse_html_table_rows(report_html)
    if len(rows) < 2:
        return {}

    header = [normalize_header_name(cell) for cell in rows[0]]
    sweater_col = find_header_index(header, ["#", "number", "num", "jersey"])
    if sweater_col is None:
        return {}

    stat_columns = {}
    for stat_key, aliases in stat_headers.items():
        stat_column = find_header_index(header, aliases)
        if stat_column is not None:
            stat_columns[stat_key] = stat_column

    if not stat_columns:
        return {}

    parsed = {}
    for row in rows[1:]:
        sweater_number = parse_int_stat(get_cell_value(row, sweater_col))
        if sweater_number is None:
            continue

        parsed_row = {}
        for stat_key, stat_column in stat_columns.items():
            parser = stat_parsers[stat_key]
            parsed_row[stat_key] = parser(get_cell_value(row, stat_column))

        parsed[sweater_number] = parsed_row

    return parsed


def parse_html_table_rows(report_html):
    if not report_html:
        return []

    table_match = re.search(HTML_TABLE_REGEX, report_html, flags=re.IGNORECASE | re.DOTALL)
    if not table_match:
        return []

    table_html = table_match.group(1)
    rows = []
    row_matches = re.findall(HTML_ROW_REGEX, table_html, flags=re.IGNORECASE | re.DOTALL)
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
