"""
Check if season is added and update only the last one, needed mostly not to erase
fw stats for previous seasons
"""

from itertools import chain
import copy
import collections
import requests
from tqdm import tqdm

from django.core.management.base import BaseCommand

from players.models import Skater
from players.models import Goalie


STAT_TYPE = 'yearByYear'
POSITIONS = ['G', 'D', 'C', 'LW', 'RW', 'L', 'R']
PL_STAT_URL_BASE = 'https://statsapi.web.nhl.com/api/v1/people/'
NHL = 'National Hockey League'


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
        players = list(chain(Goalie.objects.all(), Skater.objects.all()))
        # players = Goalie.objects.all()
        for player in tqdm(players):
            json_resp = (
                player_ind_stats(STAT_TYPE, player.nhl_id).json()['people'][0]
            )
            if not player.sbs_stats:
                data = json_resp['stats'][0]['splits']
            else:
                data = json_resp['stats'][0]['splits']#[-5:]

            # data = json_resp['stats'][0]['splits']
            import_player(data, player)


def import_player(data, player):
    """

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

            if player.position_abbr in POSITIONS[1:]:
                # Getting an average TOI from total
                season['stat']['timeOnIce'] = (
                    time_from_sec(time_to_sec(season['stat']['timeOnIce'])
                                  /season['stat']['games'])
                )

                season['stat']['powerPlayTimeOnIce'] = (
                    time_from_sec(time_to_sec(season['stat']['powerPlayTimeOnIce'])
                                  /season['stat']['games'])
                )

                season['stat']['shortHandedTimeOnIce'] = (
                    time_from_sec(time_to_sec(season['stat']['shortHandedTimeOnIce'])
                                  /season['stat']['games'])
                )
            nhl_seasons.append(season)

    multi_seasons = []
    print(player.name)

    # seasons_count = collections.Counter(item['season'] for item in nhl_seasons)
    seasons_count = collections.Counter(item['season'] for item in player.sbs_stats)
    multi_seasons = {key: value for key, value in seasons_count.items() if value > 1}

    if player.sbs_stats:
        player.sbs_stats[-1] = nhl_seasons[-1]
        # player.sbs_stats = nhl_seasons
    else:
        player.sbs_stats = nhl_seasons

    # player.sbs_stats = nhl_seasons

    player.multiteams_seasons = multi_seasons
    player.nhl_debut = player.sbs_stats[0]['season'][:4]

    if player.position_abbr == POSITIONS[0]:
        player.save(update_fields=["sbs_stats", "multiteams_seasons", "nhl_debut"])
    else:
        nhl_seasons_avg = copy.deepcopy(nhl_seasons)
        for season in nhl_seasons_avg:
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
                      /season["stat"]["games"], 2)
            )
            season["stat"]["shortHandedPoints"] = (
                round(season["stat"]["shortHandedPoints"]
                      /season["stat"]["games"], 2)
            )

            if player.sbs_stats_avg:
                player.sbs_stats_avg[-1] = nhl_seasons_avg[-1]
                # player.sbs_stats_avg = nhl_seasons_avg
            else:
                player.sbs_stats_avg = nhl_seasons_avg

            player.save(update_fields=["sbs_stats", "sbs_stats_avg",
                                       "multiteams_seasons", "nhl_debut"])

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


def get_player(nhl_id):
    """

    Args:
      nhl_id: 

    Returns:

    """
    try:
        return Goalie.objects.get(nhl_id=nhl_id)
    except Goalie.DoesNotExist:
        return Skater.objects.get(nhl_id=nhl_id)


def time_to_sec(time):
    """

    Args:
      time: 

    Returns:

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
    url = ''.join([PL_STAT_URL_BASE, str(nhl_id), api_end])
    response = requests.get(url)
    response.raise_for_status()
    return response
