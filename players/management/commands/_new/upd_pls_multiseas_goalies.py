"""
Script to fetch multi-teams seasons for goalies
"""

import requests
from tqdm import tqdm

from django.core.management.base import BaseCommand

from players.models import Goalie


URL_PLAYERS = "http://www.nhl.com/stats/rest/{}"
PL_TYPE = "goalies"
REP_TYPE = "goaliesummary"
FIRST = 1990
LAST = 2018


class Command(BaseCommand):
    """ """

    def handle(self, *args, **options):
        """

        Args:
          *args: 
          **options: 

        Returns:

        """
        print(f"\n Uploading from {REP_TYPE} {PL_TYPE} report")

        for year in tqdm(range(FIRST, LAST+1)):
            goalies = Goalie.objects.all().filter(nhl_debut__range=(FIRST, year))
            if goalies:
                print(goalies)
                season = str(year) + str(year+1)
                form_season = f"{season[:4]}-{season[6:]}"
                print(form_season)
                multi_seasons_gl = goalies.filter(multiteams_seasons__has_key=form_season)
                print(multi_seasons_gl)
                data = players_resp(REP_TYPE, PL_TYPE, season).json()["data"]
                for skater in goalies:
                    for item in data:
                        if item["playerId"] == skater.nhl_id:
                            if skater in multi_seasons_gl:
                                dict_ = {
                                    "stat": {
                                        "games": item["gamesPlayed"],
                                        "wins": item["wins"],
                                        "losses": item["losses"],
                                        "ot": item["otLosses"],
                                        "goalAgainstAverage": item["goalsAgainstAverage"],
                                        "savePercentage": item["savePctg"],
                                        "saves": item["saves"],
                                        "shutouts": item["shutouts"],
                                    },

                                    "season": f"{form_season} total",
                                    "team": {
                                        "abbr": item["playerTeamsPlayedFor"],
                                    },
                                }

                                skater.sbs_stats.insert(skater.seasons_count, dict_)
                                skater.seasons_count += (skater.multiteams_seasons[form_season])

                            skater.seasons_count += 1
                            skater.save(update_fields=["sbs_stats", "seasons_count"])

        for skater in tqdm(Goalie.objects.all()):
            skater.seasons_count = 0
            skater.save(update_fields=["seasons_count"])


def players_resp(rep_type, pl_type, season):
    """

    Args:
      rep_type: 
      pl_type: 
      season: 

    Returns:

    """
    params = {
        "isAggregate": "false",
        "reportType": "season",
        "isGame": "false",
        "reportName": rep_type,
        "cayenneExp": f"gameTypeId=2 and seasonId={season}",
    }

    return requests.get(URL_PLAYERS.format(pl_type), params=params)
