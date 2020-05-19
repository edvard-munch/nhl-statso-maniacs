import copy
import datetime
import functools
from itertools import chain

import requests
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

import players.utils as utils
from players.models import Goalie, Skater, Team

STAT_TYPE = 'careerRegularSeason'
PLAYER_ENDPOINT_URL = 'https://statsapi.web.nhl.com/api/v1/people/'
BOOL_FIELDS = ['alternateCaptain', 'captain', 'rookie']


class Command(BaseCommand):
    """ """

    def import_player(self, data, nhl_id):
        """

        Args:
          data:
          nhl_id:

        Returns:

        """
        team_name = get_data(data, ['currentTeam', 'name'])

        defaults = {
            'first_name': get_data(data, ['firstName']),
            'height': get_data(data, ['height']),
            'position_abbr': get_data(data, ['primaryPosition', 'abbreviation']),
            'position_name': get_data(data, ['primaryPosition', 'name']),
            'roster_status': get_data(data, ['rosterStatus']),
            'pl_number': get_data(data, ['primaryNumber']),
            'captain': get_data(data, ['captain']),
            'alt_captain': get_data(data, ['alternateCaptain']),
            'rookie': get_data(data, ['rookie']),
            'team': Team.objects.filter(name=team_name).first()
        }

        try:
            defaults['career_stats'] = data['stats'][0]['splits'][0]['stat']

            if defaults['position_abbr'] in utils.POSITIONS[1:]:
                stats_tot_avg = copy.deepcopy(defaults['career_stats'])

                stats_tot_avg["goals"] = get_average('goals', stats_tot_avg)
                stats_tot_avg["assists"] = get_average('assists', stats_tot_avg)
                stats_tot_avg["points"] = round(stats_tot_avg["goals"]
                                                + stats_tot_avg["assists"], 2)
                stats_tot_avg["powerPlayPoints"] = get_average('powerPlayPoints',
                                                               stats_tot_avg)
                stats_tot_avg["shortHandedPoints"] = get_average('shortHandedPoints',
                                                                 stats_tot_avg)
                stats_tot_avg["plusMinus"] = get_average('plusMinus', stats_tot_avg)
                stats_tot_avg["hits"] = get_average('hits', stats_tot_avg)
                stats_tot_avg["shots"] = get_average('shots', stats_tot_avg)
                stats_tot_avg["blocked"] = get_average('blocked', stats_tot_avg)
                stats_tot_avg["pim"] = get_average('pim', stats_tot_avg)

                defaults['career_stats_avg'] = stats_tot_avg

        except IndexError:
            print(f'{data["fullName"]} has no career stats yet')

        if defaults['position_abbr'] == utils.POSITIONS[0]:
            Goalie.objects.update_or_create(nhl_id=nhl_id, defaults=defaults)
        else:
            Skater.objects.update_or_create(nhl_id=nhl_id, defaults=defaults)

    def handle(self, *args, **options):
        """

        Args:
          *args:
          **options:

        Returns:

        """
        players = list(chain(Goalie.objects.all(), Skater.objects.all()))
        print(f'\n Uploading from {STAT_TYPE} report')
        for player in tqdm(players):
            data = player_ind_stats(STAT_TYPE, player.nhl_id).json()['people'][0]
            self.import_player(data, player.nhl_id)


def get_data(data, path):
    """
    Gets a data from an JSON source for a given list of keys

    JSON could be nested.

    Args:
      data: JSON dictionary with a data for a player
      path: a list of keys to lookup in a player's data

    Returns:
        a int/str/bool value for a given key, None if key doesn'exists
        or False if key doesn't exists for a boolean field

    Raises:
        TypeError when passing data=None to a dict.get in functools.reduce
    """
    try:
        result = functools.reduce(dict.get, path, data)
    except TypeError:
        result = None

    if result is None:
        print(f'{data["fullName"]} has no {".".join(path)} key')
        if path[0] in BOOL_FIELDS:
            result = False

    return result


def get_average(stat, stats_tot_avg):
    """

    Args:
      stat:
      stats_tot_avg:

    Returns:

    """
    return round(stats_tot_avg[stat]/stats_tot_avg["games"], 2)


def time_from_sec(time):
    """

    Args:
      time:

    Returns:

    """
    min_, sec = divmod(time, 60)
    min_ = int(min_)
    sec = str(int(sec)).zfill(2)
    return f'{min_}:{sec}'.rjust(5, '0')


def player_ind_stats(st_type, nhl_id):
    """

    Args:
      st_type:
      nhl_id:

    Returns:

    """
    api_end = f'?hydrate=stats(splits={st_type})'
    url = ''.join([PLAYER_ENDPOINT_URL, str(nhl_id), api_end])

    response = requests.get(url)
    response.raise_for_status()
    return response
