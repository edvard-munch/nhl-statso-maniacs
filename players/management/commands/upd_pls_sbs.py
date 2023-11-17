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
API_END = f'?hydrate=stats(splits={STAT_TYPE})'
NHL = 'National Hockey League'
CURRENT_SEASON_FORMAT = '2023-24'
CURRENT_SEASON = '20232024'

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
    55: 'SEA',
}


class Command(BaseCommand):
    """ """

    def handle(self, *args, **options):
        """
        Iterates every Player's object

        Invokes `player_ind_stats` and 'import_player' function

        Args:
          *args:
          **options:

        """
        if utils.season_in_prog():
            players = list(chain(Goalie.objects.all(), Skater.objects.all()))
            print(f'\n Uploading from {STAT_TYPE} report')
            for player in tqdm(players):
                json_resp = (
                    player_ind_stats(player.nhl_id).json()['people'][0]
                )
                data = json_resp['stats'][0]['splits']

                import_player(data, player)
        else:
            print('The season is over...')


def import_player(data, player):
    """
    Writes JSON with stats for every NHL season for a player

    Args:
      data:
      player:

    Returns:

    """
    nhl_seasons = []
    for season in data:
        if season['league']['name'] == NHL:
            season['season'] = format_season(season['season'])
            season['team']['abbr'] = TEAM_ABBR[season['team']['id']]
            # Getting an average TOI from total
            if player.position_abbr in utils.POSITIONS[1:]:
                season['stat']['timeOnIce'] = (
                    time_from_sec(time_to_sec(season['stat']['timeOnIce'])
                                  / season['stat']['games'])
                )

                season['stat']['powerPlayTimeOnIce'] = (
                    time_from_sec(time_to_sec(season['stat']['powerPlayTimeOnIce'])
                                  / season['stat']['games'])
                )

                season['stat']['shortHandedTimeOnIce'] = (
                    time_from_sec(time_to_sec(season['stat']['shortHandedTimeOnIce'])
                                  / season['stat']['games'])
                )

            nhl_seasons.append(season)

    player.sbs_stats = nhl_seasons

    seasons_count = collections.Counter(item['season'] for item in player.sbs_stats)
    player.multiteams_seasons = {key: value for key, value in seasons_count.items() if value > 1}
    player.nhl_debut = player.sbs_stats[0]['season'][:4]

    update_fields = ['sbs_stats', 'multiteams_seasons', 'nhl_debut']

    if player.position_abbr in utils.POSITIONS[1:]:
        player.sbs_stats_avg = copy.deepcopy(player.sbs_stats)
        update_fields.append('sbs_stats_avg')

        for season in player.sbs_stats_avg:
            season["stat"]["goals"] = (
                round(season["stat"]["goals"] / season["stat"]["games"], 2)
            )
            season["stat"]["assists"] = (
                round(season["stat"]["assists"] / season["stat"]["games"], 2)
            )
            season["stat"]["points"] = (
                round(season["stat"]["goals"] + season["stat"]["assists"], 2)
            )
            season["stat"]["plusMinus"] = (
                round(season["stat"]["plusMinus"]/season["stat"]["games"], 2)
            )
            season["stat"]["hits"] = (
                round(season["stat"]["hits"] / season["stat"]["games"], 2)
            )
            season["stat"]["shots"] = (
                round(season["stat"]["shots"] / season["stat"]["games"], 2)
            )
            season["stat"]["blocked"] = (
                round(season["stat"]["blocked"] / season["stat"]["games"], 2)
            )
            season["stat"]["pim"] = (
                round(season["stat"]["pim"] / season["stat"]["games"], 2)
            )
            season["stat"]["powerPlayPoints"] = (
                round(season["stat"]["powerPlayPoints"]
                      / season["stat"]["games"], 2)
            )
            season["stat"]["shortHandedPoints"] = (
                round(season["stat"]["shortHandedPoints"]
                      / season["stat"]["games"], 2)
            )

    player.save(update_fields=update_fields)


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


def player_ind_stats(nhl_id):
    """
    Returns a response object with the data

    Args:
      # st_type: a string that represents type of the stat report
      nhl_id: an integer representing id of a player on nhl.com API

    """
    url = ''.join([upd_pls_tot.PLAYER_ENDPOINT_URL, str(nhl_id), API_END])
    response = requests.get(url)
    response.raise_for_status()
    return response
