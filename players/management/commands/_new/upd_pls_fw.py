"""
Script to load missing FW stats for sbs and total stats. Works great but needs
to work better with upd_pls_sbs, update stats only for current season
"""

import requests
from tqdm import tqdm

from django.core.management.base import BaseCommand

from players.models import Skater


URL_PLAYERS = "http://www.nhl.com/stats/rest/{}"
PL_TYPE = "skaters"
REP_TYPE = "realtime"
FIRST = 1996
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
        print(f"\n Uploading FW from {REP_TYPE} report")

        for year in tqdm(range(FIRST, LAST+1)):
            skaters = Skater.objects.all().filter(nhl_debut__range=(FIRST, year))
            season = str(year) + str(year + 1)
            form_season = f"{season[:4]}-{season[6:]}"
            # # sk = skaters.filter(sbs_stats__has_key='stat')
            # for skater in skaters:
            #     for season in skater.sbs_stats:
            #         print(season["stat"]["faceoffsWon"])
            # print(form_season)
            # skaters = skaters.exclude(fw_stats__has_key=form_season)
            # print(skaters)
            if skaters:
                season = str(year) + str(year + 1)
                form_season = f"{season[:4]}-{season[6:]}"
                print(form_season)
                multi_seasons_sk = skaters.filter(multiteams_seasons__has_key=form_season)
                data = players_resp(REP_TYPE, PL_TYPE, season).json()["data"]
                for skater in tqdm(skaters):
                    for item in data:
                        if item["playerId"] == skater.nhl_id:
                            if skater in multi_seasons_sk:
                                if form_season not in skater.multiteams_seasons_appl or form_season[:4] == LAST:
                                    dict_ = {
                                        "stat": {
                                            "games": item["gamesPlayed"],
                                            "goals": item["goals"],
                                            "assists": sum(
                                                season["stat"]["assists"]
                                                for season
                                                in skater.sbs_stats if season["season"] == form_season
                                            ),
                                            "points": sum(
                                                season["stat"]["points"]
                                                for season
                                                in skater.sbs_stats if season["season"] == form_season
                                            ),
                                            "plusMinus": sum(
                                                season["stat"]["plusMinus"]
                                                for season
                                                in skater.sbs_stats if season["season"] == form_season
                                            ),
                                            "pim": sum(
                                                int(season["stat"]["penaltyMinutes"])
                                                for season
                                                in skater.sbs_stats if season["season"] == form_season
                                            ),
                                            "shots": item["shots"],
                                            "hits": item["hits"],
                                            "blocked": item["blockedShots"],
                                            "faceoffsWon": item["faceoffsWon"],
                                            "powerPlayPoints": sum(
                                                season["stat"]["powerPlayPoints"]
                                                for season
                                                in skater.sbs_stats if season["season"] == form_season
                                            ),
                                            "shortHandedPoints": sum(
                                                season["stat"]["shortHandedPoints"]
                                                for season
                                                in skater.sbs_stats if season["season"] == form_season
                                            ),
                                            "timeOnIce": time_from_sec(
                                                sum(time_to_sec(season["stat"]["timeOnIce"])
                                                    * season["stat"]["games"]
                                                    for season
                                                    in skater.sbs_stats if season["season"] == form_season)
                                                /item["gamesPlayed"]
                                            ),
                                            "powerPlayTimeOnIce": time_from_sec(
                                                sum(time_to_sec(season["stat"]["powerPlayTimeOnIce"])
                                                    * season["stat"]["games"]
                                                    for season
                                                    in skater.sbs_stats if season["season"] == form_season)
                                                /item["gamesPlayed"]
                                            ),
                                            "shortHandedTimeOnIce": time_from_sec(
                                                sum(time_to_sec(season["stat"]["shortHandedTimeOnIce"])
                                                    * season["stat"]["games"]
                                                    for season
                                                    in skater.sbs_stats if season["season"] == form_season)
                                                /item["gamesPlayed"]
                                            ),
                                        },

                                        "season": f"{form_season} total",
                                        "team": {
                                            "abbr": item["playerTeamsPlayedFor"],
                                        },
                                    }

                                    dict_avg = {
                                        "stat": {
                                            "games": item["gamesPlayed"],
                                            "goals": round(item["goals"]
                                                           /item["gamesPlayed"], 2),
                                            "assists": round(dict_["stat"]["assists"]
                                                             /item["gamesPlayed"], 2),
                                            "points": round(dict_["stat"]["points"]
                                                            /item["gamesPlayed"], 2),
                                            "plusMinus": round(dict_["stat"]["plusMinus"]
                                                               /item["gamesPlayed"], 2),
                                            "pim": round(dict_["stat"]["pim"]
                                                         /item["gamesPlayed"], 2),
                                            "shots": round(item["shots"]
                                                           /item["gamesPlayed"], 2),
                                            "hits": round(item["hits"]
                                                          /item["gamesPlayed"], 2),
                                            "blocked": round(item["blockedShots"]
                                                             /item["gamesPlayed"], 2),
                                            "faceoffsWon": round(item["faceoffsWon"]
                                                                 /item["gamesPlayed"], 2),
                                            "powerPlayPoints": round(dict_["stat"]["powerPlayPoints"]
                                                                     /item["gamesPlayed"], 2),
                                            "shortHandedPoints": round(dict_["stat"]["shortHandedPoints"]
                                                                       /item["gamesPlayed"], 2),
                                            "timeOnIce": dict_["stat"]["timeOnIce"],
                                            "powerPlayTimeOnIce": dict_["stat"]["powerPlayTimeOnIce"],
                                            "shortHandedTimeOnIce": dict_["stat"]["shortHandedTimeOnIce"],
                                        },

                                        "season": f"{form_season} total",
                                        "team": {
                                            "abbr": item["playerTeamsPlayedFor"],
                                        },
                                    }

                                    if form_season not in skater.multiteams_seasons_appl:
                                        skater.sbs_stats.insert(skater.seasons_count, dict_)
                                        skater.sbs_stats_avg.insert(skater.seasons_count, dict_avg)
                                    else:
                                        skater.sbs_stats[skater.seasons_count] = dict_
                                        skater.sbs_stats_avg[skater.seasons_count] = dict_avg

                                if form_season not in skater.multiteams_seasons_appl:
                                    skater.multiteams_seasons_appl.append(form_season)

                                skater.seasons_count += (skater.multiteams_seasons[form_season])

                            else:
                                skater.sbs_stats[skater.seasons_count]["stat"]["faceoffsWon"] = (
                                    item["faceoffsWon"]
                                )
                                skater.fw_stats[form_season] = item["faceoffsWon"]

                                skater.sbs_stats_avg[skater.seasons_count]["stat"]["faceoffsWon"] = (
                                    round(item["faceoffsWon"] / item["gamesPlayed"], 2)
                                )

                            skater.seasons_count += 1
                            skater.save(update_fields=["sbs_stats", "sbs_stats_avg", "seasons_count", "fw_stats", "multiteams_seasons_appl"])

        for skater in tqdm(Skater.objects.all()):
            sum_ = 0
            for item in skater.sbs_stats:
                try:
                    sum_ += item["stat"]["faceoffsWon"]
                except KeyError:
                    pass
            skater.career_stats["faceoffsWon"] = sum_
            try:
                skater.career_stats_avg["faceoffsWon"] = round(skater.career_stats["faceoffsWon"]
                                                               /skater.career_stats["games"], 2)
            except KeyError:
                print(skater.name)

            skater.seasons_count = 0
            skater.save(update_fields=["career_stats", "career_stats_avg", "seasons_count"])


def time_from_sec(time):
    """

    Args:
      time: 

    Returns:

    """
    min_, sec = divmod(time, 60)
    min_ = int(min_)
    sec = str(int(sec)).zfill(2)
    return f"{min_}:{sec}".rjust(5, "0")


def time_to_sec(time):
    """

    Args:
      time: 

    Returns:

    """
    min_sec = time.split(":")
    return int(min_sec[0])*60 + int(min_sec[1])


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
