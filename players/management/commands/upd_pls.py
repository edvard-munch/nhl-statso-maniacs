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

URL_PLAYERS = 'https://api.nhle.com/stats/rest/en/{}/{}'
URL_PLAYERS_PICS = 'https://nhl.bamcontent.com/images/headshots/current/168x168/{}.jpg'
PL_TYPE1 = "goalie"
PL_TYPE2 = "skater"
REP_TYPE1 = 'bios'
REP_TYPE2 = 'summary'
REP_TYPE3 = 'realtime'
REP_TYPE4 = 'timeonice'
REP_TYPE5 = 'faceoffwins'
PLAYERS_PICS_DIR = 'players_pics'
FLAGS_DIR = 'flags'
INCH_TO_CM_COEFF = 2.54
POUND_TO_KG_COEFF = 2.205
SEASON = '20192020'
PLAYERS_PER_PAGE = 100

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
        # print(player)

        # bios report
        # index = 0, index = 2
        id_ = player["playerId"]
        if index == 0 or index == 2:

            if player['birthStateProvinceCode'] is None:
                player['birthStateProvinceCode'] = ''

            if player["nationalityCode"] is None:
                player["nationalityCode"] = player["birthCountryCode"]

           # REMOVE
           if player["lastName"] == 'Quinney':
                print(player["birthDate"])

            birth_date = parse_date(player["birthDate"])

            # 1 diff fields for skater and goalie:
            # skaterFullName
            # goalieFullName

            # 2 no firstName field, parse from fullNAME

            defaults = {
                'last_name': get_char_field_value(player, "lastName"),
                'weight': player["weight"],
                'weight_kg': round(player["weight"] / POUND_TO_KG_COEFF),
                'birth_date': birth_date,
                'birth_city': get_char_field_value(player, "birthCity"),
                'birth_state': get_char_field_value(player, "birthStateProvinceCode"),
                'birth_country': COUNTRIES[player["birthCountryCode"]],
                'birth_country_abbr': get_char_field_value(player, "birthCountryCode"),
                'nation': COUNTRIES[player["nationalityCode"]],
                'nation_abbr': get_char_field_value(player, "nationalityCode"),
                'games': player["gamesPlayed"],
                'height_cm': round(player['height'] * INCH_TO_CM_COEFF),
                'age': calculate_age(birth_date),
            }

            defaults_dr = {}
            if player['draftOverall']:
                defaults_dr = {
                    'draft_year': player["draftYear"],
                    'draft_round': player['draftRound'],
                    'draft_number': player['draftOverall'],
                }

            defaults = {**defaults, **defaults_dr}

            # TO CONSTANT
            if 'positionCode' in player:
                player_obj = Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)[0]
            else:
                player_obj = Goalie.objects.update_or_create(nhl_id=id_, defaults=defaults)[0]

            img_name = f'{player_obj.slug}.jpg'
            flag_name = f'{player_obj.nation_abbr}.jpg'

            if pic_missing(img_name, player_obj.image, PLAYERS_PICS_DIR):
                upload_pic(player_obj, img_name, URL_PLAYERS_PICS)
            if pic_missing(flag_name, player_obj.nation_flag, FLAGS_DIR):
                print(flag_name)
                upload_flag(player_obj, flag_name)

        # goalie bios has no sv, gaa, sv%

        elif index == 1:  # goalie summary report
        # if player["playerPositionCode"] == utils.POSITIONS[0]:
            defaults = {
                'name': get_char_field_value(player, "goalieFullName"),
                # 'first_name': get_char_field_value(player, "playerFirstName"),
                'wins': player["wins"],
                'losses': player["losses"],
                'ot_losses': player["otLosses"],
                'shotouts': player["shutouts"],
                'goals_against_av': player["goalsAgainstAverage"],
                'saves_perc': player["savePct"],
                'saves': player["saves"],
            }

            Goalie.objects.update_or_create(nhl_id=id_, defaults=defaults)

        elif index == 3:  # skater summary
            defaults = {
                'name': get_char_field_value(player, "skaterFullName"),
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

            Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)

            # img_name = f'{player_obj.slug}.jpg'
            # flag_name = f'{player_obj.nation_abbr}.jpg'

            # if pic_missing(img_name, player_obj.image, PLAYERS_PICS_DIR):
            #     upload_pic(player_obj, img_name, URL_PLAYERS_PICS)
            # if pic_missing(flag_name, player_obj.nation_flag, FLAGS_DIR):
            #     upload_flag(player_obj, flag_name)

        elif index == 4:
            defaults = {
                'hits': player["hits"],
                'hits_avg': round(player["hits"] / player["gamesPlayed"], 2),
                'blocks': player["blockedShots"],
                'blocks_avg': round(player["blockedShots"] / player["gamesPlayed"], 2),
            }

            Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)

        elif index == 5:
            defaults = {
                'time_on_ice': time_from_sec(player["timeOnIcePerGame"]),
                'time_on_ice_pp': time_from_sec(player["ppTimeOnIcePerGame"]),
                'time_on_ice_sh': time_from_sec(player["shTimeOnIcePerGame"]),
            }

            Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)

        elif index == 6:
            defaults = {
                'faceoff_wins': player["totalFaceoffWins"],
                'faceoff_wins_avg': round(player["totalFaceoffWins"] / player["gamesPlayed"], 2),
            }

            Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)    


        # FACEOFFS and TOI HAVE A DIFFERENT ORDER
    def handle(self, *args, **options):
        """

        Args:
          *args:
          **options:

        Returns:

        """
        reports_list = [
            [REP_TYPE1, PL_TYPE1],  # 0 bios goalies
            [REP_TYPE2, PL_TYPE1],  # 1 summary goalies
            [REP_TYPE1, PL_TYPE2],  # 2 bios skaters
            [REP_TYPE2, PL_TYPE2],  # 3 summary skaters
            [REP_TYPE3, PL_TYPE2],  # 4 realtime skaters
            [REP_TYPE4, PL_TYPE2],  # 5 timeonice skaters
            [REP_TYPE5, PL_TYPE2],  # 6 faceoffs skaters
        ]

        for index, item in enumerate(reports_list):
            print(f'\n Uploading from {item[1]} {item[0]} report')
            start = 0   # TO CONSTANT
            data = players_resp(item[0], item[1], start).json()
            total_players = data['total']
            players_list = data['data']
            if total_players > PLAYERS_PER_PAGE:
                start += PLAYERS_PER_PAGE
                while start < total_players:
                    resp = players_resp(item[0], item[1], start).json()['data']
                    start += PLAYERS_PER_PAGE
                    players_list += resp

            for player in tqdm(players_list):
                self.import_player(player, index)


# Using tuple comparison and a fact that True == 1 and False == 0
def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def get_char_field_value(player, field):
    try:
        return player[field]
    except KeyError:
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


def players_resp(rep_type, pl_type, start_from_index):
    """
    Args:
      rep_type:
      pl_type:

    Returns:

    """
    params = {
        'isAggregate': 'false',
        # 'reportType': 'season',
        'isGame': 'false',
        'limit': PLAYERS_PER_PAGE,
        'start': start_from_index,
        # 'reportName': rep_type,
        'cayenneExp': f'gameTypeId=2 and seasonId={SEASON}',
    }

    return requests.get(URL_PLAYERS.format(pl_type, rep_type), params=params)


# https://api.nhle.com/stats/rest/en/skater/realtime?isAggregate=false&isGame=false&sort=%5B%7B%22property%22:%22hits%22,%22direction%22:%22DESC%22%7D%5D&start=0&limit=100&factCayenneExp=gamesPlayed%3E=1&cayenneExp=gameTypeId=2%20and%20seasonId%3C=20192020%20and%20seasonId%3E=20192020
