import json
import re

import requests
from django.core.management.base import BaseCommand
from django.shortcuts import get_object_or_404 as get_object
from django.utils.text import slugify
from tqdm import tqdm

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
MONTH_ORDER = ['09', '10', '11', '12', '01', '02', '03', '04', '05', '06', '07', '08']

class Command(BaseCommand):

    def handle(self, *args, **options):
        schedule = get_schedule()
        for date in tqdm(schedule):
            gameday_obj = Gameday.objects.update_or_create(day=date['date'])[0]

            for game in date["games"]:
                if str(game["gamePk"])[4:6] == REG_SEAS_CODE:
                    rosters = game_data(game["gamePk"], URL_BOXSCORE)["teams"]
                    linescore = game_data(game["gamePk"], URL_LINESCORE)

                    team_nhl_ids = [
                        linescore["teams"]['away']['team']['id'],
                        linescore["teams"]['home']['team']['id'],
                    ]

                    team_objects = [
                        Team.objects.get(nhl_id=team_nhl_ids[0]),
                        Team.objects.get(nhl_id=team_nhl_ids[1]),
                    ]

                    team_names = [item.name for item in team_objects]
                    score = f'{linescore["teams"]["away"]["goals"]}:{linescore["teams"]["home"]["goals"]}'

                    # ADD 'GAME IN PROGRESS' if it's not finished
                    if linescore['currentPeriod'] > REGULAR_PERIODS_AMOUNT:
                        if linescore['currentPeriodTimeRemaining'] == GAME_FINISHED:
                            score += f' {linescore["currentPeriodOrdinal"]}'

                    defaults = {
                        'result': f"{' - '.join(team_names)} {score}",
                        'gameday': gameday_obj,
                    }

                    game_obj, created = Game.objects.update_or_create(nhl_id=game["gamePk"], defaults=defaults)

                    if created:
                        game_obj.slug = slugify(" - ".join(team_names) + str(game_obj.gameday.day))
                        game_obj.save(update_fields=['slug'])

                    away_skaters = []
                    away_goalies = []
                    home_skaters = []
                    home_goalies = []

                    away_team = team_objects[0].abbr
                    home_team = team_objects[1].abbr

                    iterate_players(gameday_obj, rosters['away']['players'], away_skaters, away_goalies, home_team)
                    iterate_players(gameday_obj, rosters['home']['players'], home_skaters, home_goalies, away_team)

                    save_game_side(team_objects[0], SIDES['away'], game_obj, date["date"])
                    save_game_side(team_objects[1], SIDES['home'], game_obj, date["date"])

                    game_obj.away_skaters.set(away_skaters)
                    game_obj.away_goalies.set(away_goalies)
                    game_obj.home_skaters.set(home_skaters)
                    game_obj.home_goalies.set(home_goalies)


# make skaters, goalies variable names more concise
def iterate_players(gameday_obj, players, skaters, goalies, opponent):
    for key, value in players.items():
        nhl_id = int(key[2:])
        player = get_player(nhl_id)
        if player:
            val = add_player(value, player, skaters, goalies, opponent)
            format_date = date_convert(gameday_obj.day)

            if isinstance(val, dict):
               val['format_date'] = format_date

            player.gamelog_stats[str(gameday_obj.day)] = val
            
            player.save(update_fields=['gamelog_stats'])


def date_convert(date):
    date_str = date.strftime('%b %e')
    return re.sub(r'\s+', ' ', date_str)


def add_player(value, player, skaters, goalies, opponent):
    try:
        dict_ = value['stats']['skaterStats']
        dict_['powerPlayPoints'] = dict_['powerPlayGoals'] + dict_['powerPlayAssists']
        dict_['shortHandedPoints'] = dict_['shortHandedGoals'] + dict_['shortHandedAssists']
        dict_['jerseyNumber'] = value['jerseyNumber']
        dict_['opponent'] = opponent
        val = dict_
        skaters.append(player)
    except KeyError:
        try:
            dict_ = value['stats']['goalieStats']
            dict_['goalsAgainst'] = dict_['shots'] - dict_['saves']
            dict_['jerseyNumber'] = value['jerseyNumber']
            dict_['opponent'] = opponent     
            val = dict_
            goalies.append(player)
        except KeyError:
            val = 'Scratched'

    return val


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