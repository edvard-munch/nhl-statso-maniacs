from itertools import chain

import requests
from django.core.management.base import BaseCommand
from tqdm import tqdm

import players.utils as utils
from players.models import Goalie, Skater

from . import upd_pls_tot

STAT_TYPE = 'onPaceRegularSeason'


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
            data = player_ind_stats(STAT_TYPE, player.nhl_id).json()['people'][0]
            nhl_id = data["id"]
            try:
                proj_stats = data['stats'][0]['splits'][0]['stat']
                player = get_player(nhl_id=nhl_id)
                if player.position_abbr in utils.POSITIONS[1:]:
                    proj_stats["faceoff_wins"] = int(round(player.faceoff_wins_avg
                                                           * proj_stats["games"]))
                player.proj_stats = proj_stats
                player.save(update_fields=["proj_stats"])
            except IndexError:
                pass


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
