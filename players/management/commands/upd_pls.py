import os
import timeit
import urllib

import requests
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from num2words import num2words
from tqdm import tqdm
from datetime import date

import players.utils as utils
from players.models import Goalie, Skater

URL_PLAYERS = 'http://www.nhl.com/stats/rest/{}'
URL_PLAYERS_PICS = 'https://nhl.bamcontent.com/images/headshots/current/168x168/{}.jpg'
PL_TYPE1 = "goalies"
PL_TYPE2 = "skaters"
REP_TYPE1 = 'goaliesummary'
REP_TYPE2 = 'skatersummary'
REP_TYPE3 = 'realtime'
REP_TYPE4 = 'timeonice'
PLAYERS_PICS_DIR = 'players_pics'
FLAGS_DIR = 'flags'
INCH_TO_CM_COEFF = 2.54
POUND_TO_KG_COEFF = 2.205
SEASON = '20192020'

# Find a table with this, or transfer the dict to the external file
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
    'UKR': 'Ukraine',
    None: '',
}


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

        if player['playerBirthStateProvince'] is None:
            player['playerBirthStateProvince'] = ''

        birth_date = parse_date(player["playerBirthDate"])

        defaults = {
            'name': get_char_field_value(player, "playerName"),
            'first_name': get_char_field_value(player, "playerFirstName"),
            'last_name': get_char_field_value(player, "playerLastName"),
            'weight': player["playerWeight"],
            'weight_kg': round(player["playerWeight"] / POUND_TO_KG_COEFF),
            'birth_date': birth_date,
            'birth_city': get_char_field_value(player, "playerBirthCity"),
            'birth_state': get_char_field_value(player, "playerBirthStateProvince"),
            'birth_country': COUNTRIES[player["playerBirthCountry"]],
            'birth_country_abbr': get_char_field_value(player, "playerBirthCountry"),
            'nation': COUNTRIES[player["playerNationality"]],
            'nation_abbr': get_char_field_value(player, "playerNationality"),
            'games': player["gamesPlayed"],
            'height_cm': round(player['playerHeight'] * INCH_TO_CM_COEFF),
            'age': calculate_age(birth_date),
        }

        defaults_dr = {}
        if player['playerDraftOverallPickNo']:
            defaults_dr = {
                'draft_year': player["playerDraftYear"],
                'draft_round': player['playerDraftRoundNo'],
                'draft_number': player['playerDraftOverallPickNo'],
            }

        defaults = {**defaults, **defaults_dr}

        if player["playerPositionCode"] == utils.POSITIONS[0]:
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
            player_obj = Goalie.objects.update_or_create(
                nhl_id=id_, defaults=defaults)[0]
            img_name = f'{player_obj.slug}.jpg'
            flag_name = f'{player_obj.nation_abbr}.jpg'

            if pic_missing(img_name, player_obj.image, PLAYERS_PICS_DIR):
                upload_pic(player_obj, img_name, URL_PLAYERS_PICS)
            if pic_missing(flag_name, player_obj.nation_flag, FLAGS_DIR):
                upload_flag(player_obj, flag_name)

        else:
            if index == 1:
                defaults_s = {
                    'goals': player["goals"],
                    'goals_avg': round(player["goals"] / player["gamesPlayed"], 2),
                    'assists': player["assists"],
                    'assists_avg': round(player["assists"] / player["gamesPlayed"], 2),
                    'points': player["points"],
                    'points_avg': round(player["points"] / player["gamesPlayed"], 2),
                    'plus_minus': player["plusMinus"],
                    'plus_minus_avg': round(player["plusMinus"] / player["gamesPlayed"], 2),
                    'penalty_min': player["penaltyMinutes"],
                    'penalty_min_avg': round(player["penaltyMinutes"] / player["gamesPlayed"], 2),
                    'shots': player["shots"],
                    'shots_avg': round(player["shots"] / player["gamesPlayed"], 2),
                    'pp_points': player["ppPoints"],
                    'pp_points_avg': round(player["ppPoints"] / player["gamesPlayed"], 2),
                    'sh_points': player["shPoints"],
                    'sh_points_avg': round(player["shPoints"] / player["gamesPlayed"], 2),
                }
                defaults = {**defaults, **defaults_s}
                player_obj = Skater.objects.update_or_create(
                    nhl_id=id_, defaults=defaults)[0]
                img_name = f'{player_obj.slug}.jpg'
                flag_name = f'{player_obj.nation_abbr}.jpg'

                if pic_missing(img_name, player_obj.image, PLAYERS_PICS_DIR):
                    upload_pic(player_obj, img_name, URL_PLAYERS_PICS)
                if pic_missing(flag_name, player_obj.nation_flag, FLAGS_DIR):
                    upload_flag(player_obj, flag_name)

            elif index == 2:
                defaults = {
                    'hits': player["hits"],
                    'hits_avg': round(player["hits"] / player["gamesPlayed"], 2),
                    'blocks': player["blockedShots"],
                    'blocks_avg': round(player["blockedShots"] / player["gamesPlayed"], 2),
                    'faceoff_wins': player["faceoffsWon"],
                    'faceoff_wins_avg': round(player["faceoffsWon"] / player["gamesPlayed"], 2),
                }
                player_obj = Skater.objects.update_or_create(
                    nhl_id=id_, defaults=defaults)[0]

            elif index == 3:
                defaults = {
                    'time_on_ice': time_from_sec(player["timeOnIcePerGame"]),
                    'time_on_ice_pp': time_from_sec(player["ppTimeOnIcePerGame"]),
                    'time_on_ice_sh': time_from_sec(player["shTimeOnIcePerGame"]),
                }
                player_obj = Skater.objects.update_or_create(
                    nhl_id=id_, defaults=defaults)[0]

    def handle(self, *args, **options):
        """

        Args:
          *args:
          **options:

        Returns:

        """
        reports_list = [
            [REP_TYPE1, PL_TYPE1],
            [REP_TYPE2, PL_TYPE2],
            [REP_TYPE3, PL_TYPE2],
            [REP_TYPE4, PL_TYPE2],
        ]

        for index, item in enumerate(reports_list):
            print(f'\n Uploading from {item[0]} report')
            data = players_resp(item[0], item[1]).json()["data"]
            # print(players_resp(item[0], item[1]).json())

            for player in tqdm(data):
                self.import_player(player, index)


# Using tuple comparison and a fact that True == 1 and False == 0
def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def get_char_field_value(player, field):
    if player[field]:
        return player[field]
    else:
        return ''


def pic_missing(pic_name, field, dir):
    """

    Args:
      pic_name:
      field:
      dir:

    Returns:

    """
    path = os.path.join(settings.MEDIA_ROOT, dir, pic_name)
    # field.path != path should be unnecessary in production
    return not field or not os.path.isfile(path) or field.path != path


def upload_pic(object, img_name, url):
    """

    Args:
      object:
      img_name:
      url:

    Returns:

    """
    try:
        content = urllib.request.urlretrieve(
            url.format(object.nhl_id))
        pic = File(open(content[0], 'rb'))
        object.image.save(name=img_name, content=pic)

    except urllib.error.HTTPError:
        print(f'{object.name} has no picture yet')


def upload_flag(player_obj, flag_name):
    """

    Args:
      player_obj:
      flag_name:

    Returns:

    """
    path_elements = [settings.MEDIA_ROOT, FLAGS_DIR, flag_name]
    abs_file_path = os.path.join(*path_elements)
    rel_file_path = os.path.join(*path_elements[1:])

    if os.path.isfile(abs_file_path):
        player_obj.nation_flag.name = rel_file_path
        player_obj.save(update_fields=['nation_flag'])
    else:
        print(f'Country {player_obj.nation_abbr} of {player_obj.name} has no flag yet')


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


def players_resp(rep_type, pl_type):
    """

    Args:
      rep_type:
      pl_type:

    Returns:

    """
    params = {
        'isAggregate': 'false',
        'reportType': 'season',
        'isGame': 'false',
        'reportName': rep_type,
        'cayenneExp': f'gameTypeId=2 and seasonId={SEASON}',
    }

    return requests.get(URL_PLAYERS.format(pl_type), params=params)
