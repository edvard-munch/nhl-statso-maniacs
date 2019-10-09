"""
thinking of adding all sbs_stats form accumulated reports for all players every
season
"""

import os
import urllib.request as urllib

from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings

import requests
from tqdm import tqdm
from num2words import num2words

from players.models import Skater
from players.models import Goalie


URL_PLAYERS = 'http://www.nhl.com/stats/rest/{}'
URL_PLAYERS_PICS = 'https://nhl.bamcontent.com/images/headshots/current/168x168/{}.jpg'
PL_TYPE1 = "goalies"
PL_TYPE2 = "skaters"
REP_TYPE1 = 'goaliesummary'
REP_TYPE2 = 'skatersummary'
REP_TYPE3 = 'realtime'
REP_TYPE4 = 'timeonice'
POSITIONS = ['G', 'D', 'C', 'LW', 'RW', 'L', 'R']

COUNTRIES = {
    'RUS': 'Russia',
    'CAN': 'Canada',
    'USA': 'USA',
    'CZE': 'Czech Republic',
    'CSK': 'Czech Republic',
    'CHE': 'Switzerland',
    'SWE': 'Sweden',
    'FIN': 'Finland',
    'DEU': 'Germany',
    'DNK': 'Denmark',
    'AUT': 'Austria',
    'FRA': 'France',
    'ITA': 'Italia',
    'NOR': 'Norway',
    'LVA': 'Latvia',
    'SVN': 'Slovenia',
    'SVK': 'Slovakia',
    'NLD': 'Netherlands',
    'AUS': 'Australia',
    'GBR': 'Great Britain',
    'KAZ': 'Kazachstan',
    'BGR': 'Bulgaria',
    'EST': 'Estonia',
    None: '—',
}

POSITIONS = ['G', 'D', 'C', 'LW', 'RW', 'L', 'R']

COMBINATIONS = [[REP_TYPE1, PL_TYPE1], [REP_TYPE2, PL_TYPE2], [REP_TYPE3, PL_TYPE2],
                [REP_TYPE4, PL_TYPE2]]

FIRST = 1996
LAST = 1997


class Command(BaseCommand):
    """ """

    def import_player(self, player, index):
        """

        Args:
          player: 
          index: 

        Returns:

        """
        id_ = player["playerId"]
        print(player["playerName"])

        if player['playerBirthStateProvince'] is None:
            player['playerBirthStateProvince'] = ''

        defaults = {
            'name': player["playerName"],
            'team_abbr': player['playerTeamsPlayedFor'][-3:],
            'weight': player["playerWeight"],
            'birth_date': player["playerBirthDate"],
            'birth_city': player["playerBirthCity"],
            'birth_state': player["playerBirthStateProvince"],
            'birth_country': COUNTRIES[player["playerBirthCountry"]],
            'birth_country_abbr': player["playerBirthCountry"],
            'nation': COUNTRIES[player["playerNationality"]],
            'nation_abbr': player["playerNationality"],
            'games': player["gamesPlayed"],
        }

        if player['playerDraftOverallPickNo']:
            defaults_dr = {
                'draft_year': player["playerDraftYear"],
                'draft_round': num2words(player['playerDraftRoundNo'], to="ordinal_num"),
                'draft_number': num2words(player['playerDraftOverallPickNo'], to="ordinal_num"),
            }
            defaults = {**defaults, **defaults_dr}

        else:
            defaults_undr = {
                'draft_year': '—',
                'draft_round': '—',
                'draft_number': '—',
            }
            defaults = {**defaults, **defaults_undr}

        if player["playerPositionCode"] == POSITIONS[0]:
            defaults_g = {
                'wins': player["wins"],
                'losses': player["losses"],
                'ot_losses': player["otLosses"],
                'goals_against_av': player["goalsAgainstAverage"],
                'saves_perc': player["savePctg"],
                'saves': player["saves"],
                'shotouts': player["shutouts"],
            }
            defaults = {**defaults, **defaults_g}
            player_obj, created = Goalie.objects.update_or_create(nhl_id=id_, defaults=defaults)

            if self.pic_missing(player_obj):
                self.upload_pic(player_obj)

        else:
            if index == 1:
                defaults_s = {
                    'goals': player["goals"],
                    'goals_avg': player["goals"] / player["gamesPlayed"],
                    'assists': player["assists"],
                    'assists_avg': player["assists"] / player["gamesPlayed"],
                    'points': player["points"],
                    'points_avg': player["points"] / player["gamesPlayed"],
                    'plus_minus': player["plusMinus"],
                    'plus_minus_avg': player["plusMinus"] / player["gamesPlayed"],
                    'penalty_min': player["penaltyMinutes"],
                    'penalty_min_avg': player["penaltyMinutes"] / player["gamesPlayed"],
                    'shots': player["shots"],
                    'shots_avg': player["shots"] / player["gamesPlayed"],
                    'pp_points': player["ppPoints"],
                    'pp_points_avg': player["ppPoints"] / player["gamesPlayed"],
                    'sh_points': player["shPoints"],
                    'sh_points_avg': player["shPoints"] / player["gamesPlayed"],
                }
                defaults = {**defaults, **defaults_s}
                player_obj, created = Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)

                if self.pic_missing(player_obj):
                    self.upload_pic(player_obj)

            elif index == 2:
                defaults = {
                    'hits': player["hits"],
                    'hits_avg': player["hits"] / player["gamesPlayed"],
                    'blocks': player["blockedShots"],
                    'blocks_avg': player["blockedShots"] / player["gamesPlayed"],
                    'faceoff_wins': player["faceoffsWon"],
                    'faceoff_wins_avg': player["faceoffsWon"] / player["gamesPlayed"],
                }
                player_obj, created = Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)

            elif index == 3:
                defaults = {
                    'time_on_ice': time_from_sec(player["timeOnIcePerGame"]),
                    'time_on_ice_pp': time_from_sec(player["ppTimeOnIcePerGame"]),
                    'time_on_ice_sh': time_from_sec(player["shTimeOnIcePerGame"]),
                }
                player_obj, created = Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)


    def pic_missing(self, player_obj):
        """

        Args:
          player_obj: 

        Returns:

        """
        file_name = f'{player_obj.slug}.jpg'
        file_path = os.path.join(settings.MEDIA_ROOT, 'players_pics', file_name)
        # player_obj.image.path != file_path can be unnecessary in production
        return not player_obj.image or player_obj.image.path != file_path or not os.path.isfile(file_path)


    def upload_pic(self, player_obj):
        """

        Args:
          player_obj: 

        Returns:

        """
        content = urllib.urlretrieve(URL_PLAYERS_PICS.format(player_obj.nhl_id))
        pic = File(open(content[0], 'rb'))
        name_pattern = f'{player_obj.slug}.jpg'
        player_obj.image.save(name=name_pattern, content=pic)

# [WinError 32] The process cannot access the file because it is being used by another process
    def upload_flag(self, player_obj):
        """

        Args:
          player_obj: 

        Returns:

        """
        file_name = f'{player_obj.birth_country_abbr}.png'
        file_path = os.path.join(settings.MEDIA_ROOT, 'flags', file_name)
        with open(file_path) as f:
            player_obj.nation_flag.save(name=file_name, content=File(f))


    def handle(self, *args, **options):
        """

        Args:
          *args: 
          **options: 

        Returns:

        """
        for year in tqdm(range(FIRST, LAST+1)):
            season = str(year) + str(year + 1)
            for index, item in enumerate(COMBINATIONS):
                print(season)
                print(f'\n Uploading from {item[0]} report')
                data = players_resp(item[0], item[1], season).json()["data"]

                for player in tqdm(data):
                    self.import_player(player, index)


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


def players_resp(rep_type, pl_type, season):
    """

    Args:
      rep_type: 
      pl_type: 
      season: 

    Returns:

    """
    params = {
        'isAggregate': 'false',
        'reportType': 'season',
        'isGame': 'false',
        'reportName': rep_type,
        'cayenneExp':  f"gameTypeId=2 and seasonId={season}",
    }

    return requests.get(URL_PLAYERS.format(pl_type), params=params)
