import os
import urllib
from datetime import date

import requests
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from players.models import Goalie, Skater
from tqdm import tqdm



SEASON = '20232024'

URL_PLAYERS = 'https://api.nhle.com/stats/rest/en/{}/{}'
URL_PLAYERS_PICS = 'https://cms.nhl.bamgrid.com/images/headshots/current/168x168/{}.jpg'
PLAYERS_PICS_DIR = 'players_pics'
FLAGS_DIR = 'flags'

PL_TYPE1 = "goalie"
PL_TYPE2 = "skater"
REP_TYPE1 = 'bios'
REP_TYPE2 = 'summary'
REP_TYPE3 = 'realtime'
REP_TYPE4 = 'timeonice'
REP_TYPE5 = 'faceoffwins'
POS_CODE_KEY = 'positionCode'

INCH_TO_CM_COEFF = 2.54
POUND_TO_KG_COEFF = 2.205
PLAYERS_PER_PAGE = 100
START_INDEX = 0
TODAY = date.today()
REQUEST_PARAMS = {
        'isAggregate': 'false',
        'isGame': 'false',
        'limit': PLAYERS_PER_PAGE,
        'start': 0,
        'cayenneExp': f'gameTypeId=2 and seasonId={SEASON}',
        'sort': '[{"property":"lastName","direction":"ASC_CI"}, {"property":"playerId","direction":"ASC_CI"}]',
}
TIMEOUT = 3

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
    'UZB': 'Uzbekistan',
    'BLR': 'Belarus',
    None: '',
}


class Command(BaseCommand):
    """ """
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
            start = START_INDEX
            resp = get_response(item[0], item[1], start)

            while not resp or resp.status_code != 200:
                resp = get_response(item[0], item[1], start)

            response = resp.json()
            total_players = response['total']
            players_list = response['data']

            if total_players > PLAYERS_PER_PAGE:
                start += PLAYERS_PER_PAGE
                while start < total_players:
                    resp = get_response(item[0], item[1], start)

                    while not resp or resp.status_code != 200:
                        resp = get_response(item[0], item[1], start)

                    data = resp.json()['data']
                    start += PLAYERS_PER_PAGE
                    players_list += data

            for player in tqdm(players_list):
                self.import_player(player, index)


    def import_player(self, player, index):
        """

        Args:
          player:
          index:

        Returns:

        """
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
                'age': calculate_age(birth_date, TODAY),
            }

            defaults_dr = {}
            if player['draftOverall']:
                defaults_dr = {
                    'draft_year': player["draftYear"],
                    'draft_round': player['draftRound'],
                    'draft_number': player['draftOverall'],
                }

            defaults = {**defaults, **defaults_dr}

            if POS_CODE_KEY in player:
                player_obj = Skater.objects.update_or_create(nhl_id=id_, defaults=defaults)[0]
            else:
                player_obj = Goalie.objects.update_or_create(nhl_id=id_, defaults=defaults)[0]

            img_name = f'{player_obj.slug}.jpg'
            flag_name = f'{player_obj.nation_abbr}.jpg'

            if pic_missing(img_name, player_obj.image, PLAYERS_PICS_DIR):
                upload_pic(PLAYERS_PICS_DIR, player_obj, img_name, URL_PLAYERS_PICS)
            if pic_missing(flag_name, player_obj.nation_flag, FLAGS_DIR):
                upload_flag(player_obj, flag_name)

        elif index == 1:  # goalie summary report
            defaults = {
                'name': get_char_field_value(player, "goalieFullName"),
                'wins': get_num_field_value(player, "wins"),
                'losses': get_num_field_value(player, "losses"),
                'ot_losses': get_num_field_value(player, "otLosses"),
                'shotouts': get_num_field_value(player, "shutouts"),
                'goals_against_av': get_num_field_value(player, "goalsAgainstAverage"),
                'saves_perc': get_num_field_value(player, "savePct"),
                'saves': get_num_field_value(player, "saves"),
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


def get_response(rep_type, pl_type, start_from_index):
    """
    Args:
      rep_type:
      pl_type:

    Returns:

    """
    print(pl_type, rep_type)

    url = URL_PLAYERS.format(pl_type, rep_type)
    params = REQUEST_PARAMS
    params['start'] = start_from_index

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        print(resp.url)
        return resp

    except requests.HTTPError as e:  # if Not fOUND
        print(e.code)
        print('Wrong endpoint or a problem with the connection!')
        return None
    except requests.exceptions.ReadTimeout as e:
        print('Timeout!')
        return None


def calculate_age(born, today):
    # Using tuple comparison and a fact that True == 1 and False == 0
    no_birthday_this_year_yet = ((today.month, today.day) < (born.month, born.day))
    return today.year - born.year - no_birthday_this_year_yet


def get_char_field_value(player, field):
    try:
        if player[field] == None:
            return ''
        else:
            return player[field]

    except KeyError:
        return ''


def get_num_field_value(player, field):
    if player[field] == None:
        player[field] = 0
    return player[field]


def pic_missing(pic_name, field, directory):
    """

    Args:
      pic_name:
      field:
      dir:

    Returns:

    """
    path = os.path.join(settings.MEDIA_ROOT, directory, pic_name)
    # field.path != path should be unnecessary in production
    return not field or not os.path.isfile(path) or field.path != path


def upload_pic(directory, object, img_name, url):
    """

    Args:
      object:
      img_name:
      url:

    Returns:

    """

    path = os.path.join(settings.MEDIA_ROOT, directory, img_name)

    if os.path.isfile(path):
        pic = File(open(path, 'rb'))
        object.image.save(name=img_name, content=pic)
    else:
        try:
            if directory == upd_tms.TEAMS_LOGOS_DIR:
                id_string = object.abbr

            else:
                id_string = object.nhl_id

            content = urllib.request.urlretrieve(
                url.format(id_string))

            pic = File(open(content[0], 'rb'))
            object.image.save(name=img_name, content=pic)

        except urllib.error.HTTPError:
            print(f'{object.name} has no picture yet')

        except urllib.error.URLError:
            print('Request failed')


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
