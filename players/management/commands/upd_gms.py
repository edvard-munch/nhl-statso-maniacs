import re
from tqdm import tqdm
import requests
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from datetime import datetime, timedelta
from pytz import timezone

from players.models import Game, Gameday, Goalie, Side, Skater, Team

DATE_REGEX = r'^(\d{4})\-(\d{2})\-(\d{2})'
URL_BOXSCORE = "http://statsapi.web.nhl.com/api/v1/game/{}/boxscore"
URL_LINESCORE = "http://statsapi.web.nhl.com/api/v1/game/{}/linescore"
URL_SCHED = "https://statsapi.web.nhl.com/api/v1/schedule"
REG_SEAS_CODE = '02'
SEASON_START = "2019-10-02"


SEASON_END = "2020-04-04"
REGULAR_PERIODS_AMOUNT = 3
GAME_FINISHED = 'Final'
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
MONTHS_ORDER = ['09', '10', '11', '12', '01', '02', '03', '04', '05', '06', '07', '08']
TIMEZONE = 'US/Pacific'
DELTA_RANGE = range(1, 2)


class Command(BaseCommand):

    def handle(self, *args, **options):
        schedule = get_schedule()
        for date in tqdm(schedule):
            date_api = datetime.strptime(date['date'], '%Y-%m-%d').date()
            date_db = Gameday.objects.filter(day=date_api).first()
    
            today = datetime.now(timezone(TIMEZONE)).date()
            days_range = [today]
            for delta in DELTA_RANGE:
                days_range.append(today - timedelta(days=delta))

            if not date_db or date_db.day in days_range:
                gameday_obj = Gameday.objects.update_or_create(day=date_api)[0]
                print(gameday_obj.day)
                for game in date["games"]:
                    if str(game["gamePk"])[4:6] == REG_SEAS_CODE:
                        rosters = game_data(game["gamePk"], URL_BOXSCORE)["teams"]
                        linescore = game_data(game["gamePk"], URL_LINESCORE)

                        team_nhl_ids = [
                            linescore["teams"]['away']['team']['id'],
                            linescore["teams"]['home']['team']['id'],
                        ]

                        away_goalies_count = len(rosters['away']['goalies'])
                        home_goalies_count = len(rosters['home']['goalies'])

                        team_objects = [
                            Team.objects.get(nhl_id=team_nhl_ids[0]),
                            Team.objects.get(nhl_id=team_nhl_ids[1]),
                        ]

                        team_names = [item.name for item in team_objects]
                        away_score = linescore["teams"]["away"]["goals"]
                        home_score = linescore["teams"]["home"]["goals"]
                        score = f'{away_score}:{home_score}'

                        # ADD 'GAME IN PROGRESS' if it's not finished
                        if linescore['currentPeriod'] > REGULAR_PERIODS_AMOUNT:
                            if linescore['currentPeriodTimeRemaining'] == GAME_FINISHED:
                                score += f' {linescore["currentPeriodOrdinal"]}'

                        defaults = {
                            'result': f"{' - '.join(team_names)} {score}",
                            'gameday': gameday_obj,
                        }

                        game_obj, created = Game.objects.update_or_create(nhl_id=game["gamePk"],
                                                                          defaults=defaults)

                        if created:
                            game_obj.slug = slugify(" - ".join(team_names) + str(game_obj.gameday.day))
                            game_obj.save(update_fields=['slug'])

                        away_skaters = []
                        away_goalies = []
                        home_skaters = []
                        home_goalies = []

                        away_team = team_objects[0].abbr
                        home_team = team_objects[1].abbr

                        iterate_players(gameday_obj, rosters['away']['players'], away_skaters,
                                        away_goalies, home_team, away_goalies_count)
                        iterate_players(gameday_obj, rosters['home']['players'], home_skaters,
                                        home_goalies, away_team, home_goalies_count)

                        save_game_side(team_objects[0], SIDES['away'], game_obj, date["date"])
                        save_game_side(team_objects[1], SIDES['home'], game_obj, date["date"])

                        game_obj.away_skaters.set(away_skaters)
                        game_obj.away_goalies.set(away_goalies)
                        game_obj.home_skaters.set(home_skaters)
                        game_obj.home_goalies.set(home_goalies)


def iterate_players(gameday_obj, roster, skaters_list, goalies_list, opponent, goalies_count):
    for key, value in roster.items():
        nhl_id = int(key[2:])
        player = get_player(nhl_id)
        if player:
            game_stats = add_player(value, player, skaters_list, goalies_list, opponent, goalies_count)
            format_date = date_convert(gameday_obj.day)

            # chek if not 'Scratched'
            if game_stats:
                game_stats['format_date'] = format_date
                player.gamelog_stats[str(gameday_obj.day)] = game_stats
                player.save(update_fields=['gamelog_stats'])


def date_convert(date):
    date_str = date.strftime('%b %e')
    return re.sub(r'\s+', ' ', date_str)


def add_player(value, player, skaters_list, goalies_list, opponent, goalies_count):
    try:
        game_stats = value['stats']['skaterStats']
        game_stats['powerPlayPoints'] = game_stats['powerPlayGoals'] + game_stats['powerPlayAssists']
        game_stats['shortHandedPoints'] = game_stats['shortHandedGoals'] + game_stats['shortHandedAssists']
        add_values(game_stats, value['jerseyNumber'], opponent)

        skaters_list.append(player)

    except KeyError:
        try:
            game_stats = value['stats']['goalieStats']
            game_stats['goalsAgainst'] = game_stats['shots'] - game_stats['saves']
            game_stats['savePercentage'] = game_stats['savePercentage'] / 100
            add_values(game_stats, value['jerseyNumber'], opponent)

            if game_stats['goalsAgainst'] == 0 and goalies_count == 1:
                game_stats['shutout'] = 1
            else:
                game_stats['shutout'] = 0

            goalies_list.append(player)
 
        except KeyError:
            return None

    return game_stats


def add_values(game_stats, jersey_number, opponent):
    game_stats['jerseyNumber'] = jersey_number
    game_stats['opponent'] = opponent


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


def game_data(game_id, url):
    return requests.get(url.format(game_id)).json()


def get_schedule():
    params = {
        "startDate": SEASON_START,
        "endDate": SEASON_END,
    }
    return requests.get(URL_SCHED, params=params).json()["dates"]