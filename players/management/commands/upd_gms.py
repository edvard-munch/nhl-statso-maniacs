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

                    iterate_players(gameday_obj, rosters['away']['players'], away_skaters, away_goalies)
                    iterate_players(gameday_obj, rosters['home']['players'], home_skaters, home_goalies)

                    save_game_side(team_objects[0], 'away', game_obj, date["date"])
                    save_game_side(team_objects[1], 'home', game_obj, date["date"])

                    game_obj.away_skaters.set(away_skaters)
                    game_obj.away_goalies.set(away_goalies)
                    game_obj.home_skaters.set(home_skaters)
                    game_obj.home_goalies.set(home_goalies)


def iterate_players(gameday_obj, players, skaters, goalies):
    for key, value in players.items():
        nhl_id = int(key[2:])
        player = get_player(nhl_id)
        if player:
            val = add_player(value, player, skaters, goalies)

            player.new_gamelog_stats[str(gameday_obj.day)] = val
            player.save(update_fields=['new_gamelog_stats'])


def add_player(value, player, skaters, goalies):
    try:
        dict = value['stats']['skaterStats']
        dict['powerPlayPoints'] = dict['powerPlayGoals'] + dict['powerPlayAssists']
        dict['shortHandedPoints'] = dict['shortHandedGoals'] + dict['shortHandedAssists']
        dict['jerseyNumber'] = value['jerseyNumber']
        val = dict
        skaters.append(player)
    except KeyError:
        try:
            dict = value['stats']['goalieStats']
            dict['goalsAgainst'] = dict['shots'] - dict['saves']
            dict['jerseyNumber'] = value['jerseyNumber']
            val = dict
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
