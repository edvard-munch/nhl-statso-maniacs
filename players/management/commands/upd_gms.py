import re
from datetime import datetime, timedelta

import requests
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from players.models import Game, Gameday, Goalie, Side, Skater, Team
from pytz import timezone

ZERO_TOI = "00:00"
DATE_REGEX = r'^(\d{4})\-(\d{2})\-(\d{2})'

# get winning goalie
URL_SCHEDULE = "https://api-web.nhle.com/v1/schedule/{}"
URL_BOXSCORE = "https://api-web.nhle.com/v1/gamecenter/{}/boxscore"
REGULAR_SEASON_CODE = '02'
REGULAR_PERIODS_AMOUNT = 3

GAME_STATES = {
    'scheduled': 'FUT',
    'critical': 'CRIT',
    'pregame': 'PRE',
    'live': 'LIVE',
    'softFinal': 'OVER',
    'hard_final': 'FINAL',
    'finished': 'OFF',
}
GAME_LIVE_SUFFIX = f" ({GAME_STATES['live'].capitalize()})"

SIDES = {
    'away': 'away',
    'home': 'home',
}
MONTHS_MAP = {
    'Jan': 6,
    'Feb': 7,
    'Mar': 8,
    'Apr': 9,
    'May': 10,
    'Jun': 11,
    'Jul': 12,
    'Aug': 1,
    'Sep': 2,
    'Oct': 3,
    'Nov': 4,
    'Dec': 5,
}
MONTHS_ORDER = [
    '09', '10', '11', '12', '01', '02', '03', '04', '05', '06', '07', '08'
]
TIMEZONE = 'US/Pacific'


class Command(BaseCommand):

    def handle(self, *args, **options):
        today = datetime.now(timezone(TIMEZONE)).date()
        schedule = get_schedule(today)
        regular_season_end_date = datetime_from_string(
            schedule['regularSeasonEndDate'])

        first_unfinished_gameday_in_db = Gameday.objects.filter(
            all_games_finished=False).order_by('day').first()

        first_notloaded_gameday_in_db = Gameday.objects.filter(
            all_games_uploaded=False).order_by('day').first()

        if first_unfinished_gameday_in_db:
            check_for_games(first_unfinished_gameday_in_db.day, today)

        if first_notloaded_gameday_in_db:
            check_for_games(first_notloaded_gameday_in_db.day,
                            regular_season_end_date)


def check_for_games(date, date_end):
    while date <= date_end:
        schedule = get_schedule(date)

        for weekday in schedule['gameWeek']:
            date = datetime_from_string(weekday['date'])

            if date > date_end:
                return

            if weekday['games']:
                print(f"{weekday['date']} games loading")
                process_games(weekday)

        next_start_date = schedule.get('nextStartDate')
        if next_start_date:
            date = datetime_from_string(next_start_date)
        else:
            print('Season is over')
            return


def datetime_from_string(date_string):
    return datetime.strptime(date_string, '%Y-%m-%d').date()


def regular_season_game(game):
    return str(game["id"])[4:6] == REGULAR_SEASON_CODE


def process_games(day):
    date_api = datetime_from_string(day['date'])

    gameday_obj = Gameday.objects.update_or_create(day=date_api)[0]
    game_db = len(gameday_obj.games.all())
    games_api = len(day['games'])

    if (games_api > 0) and (game_db == games_api):
        gameday_obj.all_games_uploaded = True
        gameday_obj.save(update_fields=['all_games_uploaded'])

    games_finished_total = 0
    for game in day["games"]:
        game_finished = False
        if regular_season_game(game):
            game_data = get_game_data(game["id"], URL_BOXSCORE)

            team_nhl_ids = [
                game_data['awayTeam']['id'],
                game_data['homeTeam']['id'],
            ]

            team_objects = [
                Team.objects.get(nhl_id=team_nhl_ids[0]),
                Team.objects.get(nhl_id=team_nhl_ids[1]),
            ]

            team_names = [item.name for item in team_objects]
            score = ''

            if game_data['gameState'] != GAME_STATES['scheduled']:
                rosters_api = game_data["boxscore"]["playerByGameStats"]

                rosters_api['awayTeam']['goalies'] = get_played_goalies(
                    rosters_api['awayTeam']['goalies'])
                rosters_api['homeTeam']['goalies'] = get_played_goalies(
                    rosters_api['homeTeam']['goalies'])

                away_goalies_count = len(rosters_api['awayTeam']['goalies'])
                home_goalies_count = len(rosters_api['homeTeam']['goalies'])

                away_score = game_data["boxscore"]["linescore"]["totals"][
                    "away"]
                home_score = game_data["boxscore"]["linescore"]["totals"][
                    "home"]
                score = f'{away_score}:{home_score}'

                if game_data['gameState'] == GAME_STATES['live']:
                    score += GAME_LIVE_SUFFIX

                if game_data['period'] > REGULAR_PERIODS_AMOUNT:
                    if game_data['gameState'] == GAME_STATES['finished']:
                        score += f' {game_data["gameOutcome"]["lastPeriodType"]}'

                games_finished_total += 1
                game_finished = True

            defaults = {
                'result': f"{' - '.join(team_names)} {score}",
                'gameday': gameday_obj,
                'game_finished': game_finished,
            }

            game_obj, created = Game.objects.update_or_create(
                nhl_id=game["id"], defaults=defaults)

            if created:
                game_obj.slug = slugify(" - ".join(team_names) +
                                        str(game_obj.gameday.day))
                game_obj.save(update_fields=['slug'])

            if game_data['gameState'] != GAME_STATES['scheduled']:
                away_skaters = [[], []]
                home_skaters = [[], []]
                away_goalies = []
                home_goalies = []

                away_team = team_objects[0]
                home_team = team_objects[1]

                iterate_players(gameday_obj, rosters_api['awayTeam'],
                                away_skaters, away_goalies, away_team,
                                home_team, away_goalies_count)
                iterate_players(gameday_obj, rosters_api['homeTeam'],
                                home_skaters, home_goalies, home_team,
                                away_team, home_goalies_count)
                rosters_database = {
                    'away_team': [away_skaters, away_goalies],
                    'home_team': [home_skaters, home_goalies]
                }
                if rosters_equal(rosters_api, rosters_database):
                    games_finished_total += 1
                    game_finished = True

                game_obj.away_defencemen.set(away_skaters[0])
                game_obj.away_forwards.set(away_skaters[1])
                game_obj.away_goalies.set(away_goalies)

                game_obj.home_defencemen.set(home_skaters[0])
                game_obj.home_forwards.set(home_skaters[1])
                game_obj.home_goalies.set(home_goalies)

            save_game_side(team_objects[0], SIDES['away'], game_obj,
                           day["date"])
            save_game_side(team_objects[1], SIDES['home'], game_obj,
                           day["date"])

    if (games_api > 0) and (games_finished_total == games_api):
        gameday_obj.all_games_finished = True
        gameday_obj.save(update_fields=['all_games_finished'])


def rosters_equal(rosters_api, rosters_database):
    roster_home_team_db_length = len(
        rosters_database['home_team'][0][0]) + len(
        rosters_database['home_team'][0][1]) + len(
        rosters_database['home_team'][1])

    roster_home_team_api_length = len(
        rosters_api['homeTeam']['forwards']) + len(
        rosters_api['homeTeam']['defense']) + len(
        rosters_api['homeTeam']['goalies'])

    roster_away_team_db_length = len(
        rosters_database['away_team'][0][0]) + len(
        rosters_database['away_team'][0][1]) + len(
        rosters_database['away_team'][1])

    roster_away_team_api_length = len(
        rosters_api['awayTeam']['forwards']) + len(
        rosters_api['awayTeam']['defense']) + len(
        rosters_api['awayTeam']['goalies'])

    return (roster_home_team_db_length ==
            roster_home_team_api_length) and (roster_away_team_db_length ==
                                              roster_away_team_api_length)


def get_played_goalies(goalies):
    return [goalie for goalie in goalies if goalie["toi"] != ZERO_TOI]


def get_schedule(date):
    return requests.get(URL_SCHEDULE.format(date)).json()


def iterate_players(gameday_obj, roster, skaters_list, goalies_list, team,
                    opponent, goalies_count):
    for _, value in roster.items():
        for player_data in value:
            player = get_player(player_data['playerId'])

            if player:
                game_stats = add_player(player_data, player, skaters_list,
                                        goalies_list, team, opponent,
                                        goalies_count)
                format_date = date_convert(gameday_obj.day)

                # chek if not 'Scratched'
                if game_stats:
                    game_stats['format_date'] = format_date
                    player.gamelog_stats[str(gameday_obj.day)] = game_stats
                    player.save(update_fields=['gamelog_stats'])
            else:
                print('ERROR')
                logger.debug(
                    f"{player_data['name']['default']} not found and will not be added to the game"
                )


def date_convert(date):
    date_str = date.strftime('%b %e')
    return re.sub(r'\s+', ' ', date_str)


def add_player(player_data, player, skaters_list, goalies_list, team, opponent,
               goalies_count):
    if player_data['position'] == 'G':
        if player_data['goalsAgainst'] == 0 and goalies_count == 1:
            player_data['shutout'] = 1
        else:
            player_data['shutout'] = 0

        add_values(player_data, team, opponent, player)

        goalies_list.append(player)

    elif player_data['position'] == 'D':
        add_values(player_data, team, opponent, player)
        skaters_list[0].append(player)
    else:
        add_values(player_data, team, opponent, player)
        skaters_list[1].append(player)

    return player_data


def add_values(game_stats, team, opponent, player):
    game_stats['player'] = {}
    game_stats['player']['nhl_id'] = player.nhl_id
    game_stats['player']['slug'] = player.slug
    game_stats['player']['name'] = player.name
    game_stats['team'] = {}
    game_stats['team']['name'] = team.name
    game_stats['team']['abbr'] = team.abbr
    game_stats['opponent'] = {}
    game_stats['opponent']['name'] = opponent.name
    game_stats['opponent']['abbr'] = opponent.abbr


def save_game_side(team, side, game, date):
    defaults = {
        'team': team,
        'side': side,
        'game': game,
    }

    Side.objects.update_or_create(nhl_side_id=get_gameside_id(date, team),
                                  defaults=defaults)


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
        return Skater.objects.select_related('team').get(nhl_id=nhl_id)
    except Skater.DoesNotExist:
        try:
            return Goalie.objects.select_related('team').get(nhl_id=nhl_id)
        except Goalie.DoesNotExist:
            return None


def get_game_data(game_id, url):
    return requests.get(url.format(game_id)).json()
