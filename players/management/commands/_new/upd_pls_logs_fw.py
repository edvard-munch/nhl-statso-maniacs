"""
Script to iterate every game page and scrape fw stats for game logs
"""

import requests
from tqdm import tqdm

from django.core.management.base import BaseCommand
from django.shortcuts import get_object_or_404 as get_object

from players.models import Skater

URL_GAMES = "http://statsapi.web.nhl.com/api/v1/game/{}/boxscore"
URL_SCHED = "https://statsapi.web.nhl.com/api/v1/schedule"
REG_SEAS_CODE = '02'
SEASON_START = "2018-10-01"
SEASON_END = "2018-10-10"


class Command(BaseCommand):
    """ """

    def handle(self, *args, **options):
        """

        Args:
          *args: 
          **options: 

        Returns:

        """
        games_ids = get_games_ids()
        for game_id in tqdm(games_ids):
            print(game_id)
            rosters = game_resp(game_id)
            for roster in rosters.values():
                for player in roster["players"].values():
                    if player["position"]["code"] != "G" and player["stats"]:
                        skater_obj = (
                            get_object(Skater, nhl_id=player["person"]["id"])
                        )

                        for game in skater_obj.gamelog_stats:
                            if game["game"]["gamePk"] == game_id:
                                game["stat"]["faceOffWins"] = (
                                    player["stats"]["skaterStats"]["faceOffWins"]
                                )

                        print(skater_obj)
                        skater_obj.save(update_fields=["gamelog_stats"])


def game_resp(game_id):
    """

    Args:
      game_id: 

    Returns:

    """
    return requests.get(URL_GAMES.format(game_id)).json()["teams"]


def get_games_ids():
    """ """
    game_ids = []
    dates = games_id_resp()
    for date in dates:
        for game in date["games"]:
            if str(game["gamePk"])[4:6] == REG_SEAS_CODE:
                game_ids.append(game["gamePk"])
    return game_ids


def games_id_resp():
    """ """
    params = {
        "startDate": SEASON_START,
        "endDate": SEASON_END,
    }
    return requests.get(URL_SCHED, params=params).json()["dates"]
