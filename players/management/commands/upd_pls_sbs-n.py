"""
Just to test updating only last season
"""
import collections
import copy
from itertools import chain

import requests
from django.core.management.base import BaseCommand
from tqdm import tqdm

import players.utils as utils
from players.models import Goalie, Skater

from . import upd_pls_tot

STAT_TYPE = 'yearByYear'
NHL = 'National Hockey League'
CURRENT_SEASON_FORMAT = '2018-19'
CURRENT_SEASON = '20182019'


TEAM_ABBR = {
    1: 'NJD',
    2: 'NYI',
    3: 'NYR',
    4: 'PHI',
    5: 'PIT',
    6: 'BOS',
    7: 'BUF',
    8: 'MTL',
    9: 'OTT',
    10: 'TOR',
    11: '',
    12: 'CAR',
    13: 'FLA',
    14: 'TBL',
    15: 'WSH',
    16: 'CHI',
    17: 'DET',
    18: 'NSH',
    19: 'STL',
    20: 'CGY',
    21: 'COL',
    22: 'EDM',
    23: 'VAN',
    24: 'ANA',
    25: 'DAL',
    26: 'LAK',
    27: '',
    28: 'SJS',
    29: 'CBJ',
    30: 'MIN',
    52: 'WPG',
    53: 'ARI',
    54: 'VGK',
}


class Command(BaseCommand):
    """ """

    def handle(self, *args, **options):
        """

        Args:
          *args:
          **options:

        Returns:

        """
        # if utils.season_in_prog():
        players = Goalie.objects.all()
        print(f'\n Uploading from {STAT_TYPE} report')
        for player in tqdm(players):
            json_resp = (
                player_ind_stats(STAT_TYPE, player.nhl_id).json()['people'][0]
            )
            data = json_resp['stats'][0]['splits']
            data = [season for season in data if season['season'] == CURRENT_SEASON]
            import_player(data, player)


def import_player(data, player):
    """

    Args:
      data:
      player:

    Returns:

    """
    for index, season in enumerate(player.sbs_stats):
        for api_season in data:
            if season['season'] == format_season(api_season['season']) and api_season['league']['name'] == NHL:
                if season['team']['name'] == api_season['team']['name']:
                    print(player.name)
                    print(api_season['team']['name'])
                    player.sbs_stats[index] = api_season
                    player.sbs_stats[index]['season'] = format_season(player.sbs_stats[index]['season'])
                    player.sbs_stats[index]['team']['abbr'] = TEAM_ABBR[player.sbs_stats[index]['team']['id']]
                    break

                else:
                    # Не добавляет сезон, которого не хватает
                    print(api_season['league']['name'])
                    player.sbs_stats.append(api_season)
                    player.sbs_stats[index]['season'] = format_season(player.sbs_stats[index]['season'])
                    player.sbs_stats[index]['team']['abbr'] = TEAM_ABBR[player.sbs_stats[index]['team']['id']]
                    break

    update_fields = ['sbs_stats']
    player.save(update_fields=update_fields)


def time_from_sec(time):
    """

    Args:


    Returns:


    """
    min_, sec = divmod(time, 60)
    min_ = int(min_)
    sec = str(int(sec)).zfill(2)
    return f'{min_}:{sec}'.rjust(5, '0')


def time_to_sec(time):
    """
    Converts time to integer

    Args:
      time: string representing duration in format 'min:sec'

    Returns:
        Integer representing time in seconds

    """
    min_sec = time.split(':')
    return int(min_sec[0])*60 + int(min_sec[1])


def format_season(season):
    """

    Args:
      season:

    Returns:

    """
    return f'{season[:4]}-{season[6:]}'


def player_ind_stats(st_type, nhl_id):
    """

    Args:
      st_type:
      nhl_id:

    Returns:

    """
    api_end = f'?hydrate=stats(splits={st_type})'
    url = ''.join([upd_pls_tot.PLAYER_ENDPOINT_URL, str(nhl_id), api_end])
    response = requests.get(url)
    response.raise_for_status()
    return response
