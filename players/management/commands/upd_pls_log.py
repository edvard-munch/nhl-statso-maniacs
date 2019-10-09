import datetime
import re
from itertools import chain

import requests
from django.core.management.base import BaseCommand
from tqdm import tqdm

import players.utils as utils
from players.models import Goalie, Skater

from . import upd_pls_sbs, upd_pls_tot

STAT_TYPE = 'gameLog'


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
        print(f'\n Uploading from {STAT_TYPE} report')
        for player in tqdm(players):
            json_resp = player_ind_stats(STAT_TYPE, player.nhl_id).json()['people'][0]
            data = json_resp['stats'][0]['splits']
            import_player(data, player)


def import_player(data, player):
    """

    Args:
      data: 
      player: 

    Returns:

    """
    for game in data:
        game['date'] = date_convert(game['date'])
        game['player'] = {}
        game['player']['name'] = player.name
        game['player']['nhl_id'] = player.nhl_id
        game['player']['slug'] = player.slug
        game['team']['abbr'] = upd_pls_sbs.TEAM_ABBR[game["team"]["id"]]
        game["opponent"]["id"] = upd_pls_sbs.TEAM_ABBR[game["opponent"]["id"]]

    player.gamelog_stats = data
    player.save(update_fields=["gamelog_stats"])


def date_convert(date):
    """

    Args:
      date: 

    Returns:

    """
    datetime_obj = datetime.datetime.strptime(date, '%Y-%m-%d')
    date_str = datetime_obj.strftime('%b %e')
    return re.sub(r'\s+', ' ', date_str)


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
