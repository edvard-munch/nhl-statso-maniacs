import copy
import collections
import datetime
from itertools import chain
import urllib
from django.core.files import File

import requests
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

from players.models import Goalie, Skater
from . import upd_pls


PLAYER_ENDPOINT_URL = 'https://api-web.nhle.com/v1/player/{}/landing'
PLAYERS_PICS_DIR = 'players_pics'

INCH_TO_FEET_COEFFICIENT = 12
POSITION_CODES = {
    'G': 'Goalie',
    'D': 'Defenseman',
    'L': 'Left winger',
    'C': 'Center',
    'R': 'Right winger',
}
WINGERS_POSITION_CODES = ['L', 'R', 'W']
REGULAR_SEASON_CODE = 2
NHL_LEAGUE_CODE = 'NHL'

TEAM_ABBR_FROM_NAME = {
    'Anaheim Ducks': 'ANA',
    'Arizona Coyotes': 'ARI',
    'Atlanta Thrashers': 'ATL',
    'Boston Bruins': 'BOS',
    'Buffalo Sabres': 'BUF',
    'Calgary Flames': 'CGY',
    'Carolina Hurricanes': 'CAR',
    'Chicago Blackhawks': 'CHI',
    'Colorado Avalanche': 'COL',
    'Columbus Blue Jackets': 'CBJ',
    'Dallas Stars': 'DAL',
    'Detroit Red Wings': 'DET',
    'Edmonton Oilers': 'EDM',
    'Florida Panthers': 'FLA',
    'Los Angeles Kings': 'LAK',
    'Minnesota Wild': 'MIN',
    'Montréal Canadiens': 'MTL',
    'Nashville Predators': 'NSH',
    'New Jersey Devils': 'NJD',
    'New York Islanders': 'NYI',
    'New York Rangers': 'NYR',
    'Ottawa Senators': 'OTT',
    'Philadelphia Flyers': 'PHI',
    'Phoenix Coyotes': 'PHO',
    'Pittsburgh Penguins': 'PIT',
    'San Jose Sharks': 'SJS',
    'Seattle Kraken': 'SEA',
    'St. Louis Blues': 'STL',
    'Tampa Bay Lightning': 'TBL',
    'Toronto Maple Leafs': 'TOR',
    'Vancouver Canucks': 'VAN',
    'Vegas Golden Knights': 'VGK',
    'Washington Capitals': 'WSH',
    'Winnipeg Jets': 'WPG'
}


class Command(BaseCommand):
    def handle(self, *args, **options):
        players = list(chain(Goalie.objects.all(), Skater.objects.all()))

        for player in tqdm(players):
            print(f'\n Uploading from {player.name} page')
            data = get_response(player.nhl_id).json()
            import_player(data, player)


def import_player(data, player):
    image_name = f'{player.slug}.png'

    if upd_pls.pic_missing(image_name, player.image, PLAYERS_PICS_DIR):
        upload_profile_image(data['headshot'], player, image_name)

    defaults = {
        'first_name': data['firstName']['default'],
        'height': inches_to_feet(int(data['heightInInches'])),
        'height_cm': data['heightInCentimeters'],
        'weight': data['weightInPounds'],
        'weight_kg': data['weightInKilograms'],
        'pl_number': data['sweaterNumber'],
        'position_abbr': get_position_abbreviation(data['position']),
        'position_name': POSITION_CODES[data['position']],
    }

    defaults['career_stats'] = data['careerTotals']['regularSeason']
    defaults['sbs_stats'] = get_season_by_season_stats(data['seasonTotals'], data['position'])

    seasons_count = collections.Counter(item['season'] for item in defaults['sbs_stats'])
    defaults['multiteams_seasons'] = {key: value for key, value in seasons_count.items() if value > 1}

    if data['position'] in list(POSITION_CODES.keys())[1:]:
        career_stats = copy.deepcopy(defaults['career_stats'])
        sbs_stats = copy.deepcopy(defaults['sbs_stats'])

        defaults['career_stats_avg'] = get_career_average_stats(career_stats)
        defaults['sbs_stats_avg'] = get_season_by_season_average_stats(sbs_stats)
        Skater.objects.update_or_create(nhl_id=player.nhl_id, defaults=defaults)

    else:
        saves = defaults['career_stats']['shotsAgainst'] - defaults['career_stats']['goalsAgainst']
        defaults['career_stats']['saves'] = saves

        Goalie.objects.update_or_create(nhl_id=player.nhl_id, defaults=defaults)


def upload_profile_image(image_url, player_object, image_name):
    content = urllib.request.urlretrieve(image_url)
    pic = File(open(content[0], 'rb'))

    player_object.image.save(name=image_name, content=pic)


def get_response(nhl_id):
    return requests.get(PLAYER_ENDPOINT_URL.format(nhl_id))


def get_career_average_stats(career_stats_average):
    career_stats_average["goals"] = get_average('goals', career_stats_average)
    career_stats_average["assists"] = get_average('assists', career_stats_average)
    career_stats_average["points"] = get_average('points', career_stats_average)
    career_stats_average["powerPlayPoints"] = get_average('powerPlayPoints',
                                                   career_stats_average)
    career_stats_average["shorthandedPoints"] = get_average('shorthandedPoints',
                                                     career_stats_average)
    career_stats_average["plusMinus"] = get_average('plusMinus', career_stats_average)
    career_stats_average["shots"] = get_average('shots', career_stats_average)
    career_stats_average["pim"] = get_average('pim', career_stats_average)

    return career_stats_average


def get_season_by_season_stats(seasons_data, position_code):
    nhl_seasons = []
    for season in seasons_data:
        if season['leagueAbbrev'] == NHL_LEAGUE_CODE and season['gameTypeId'] == REGULAR_SEASON_CODE:
            season['season'] = format_season(str(season['season']))
            try:
                season['teamAbbr'] = TEAM_ABBR_FROM_NAME[season['teamName']['default']]
            except KeyError as e:
                print(e)

            if position_code == list(POSITION_CODES.keys())[0]:
                season['saves'] = season['shotsAgainst'] - season['goalsAgainst']

            nhl_seasons.append(season)

    return nhl_seasons


def get_season_by_season_average_stats(nhl_regular_seasons_data):
    for season in nhl_regular_seasons_data:
        season["goals"] = get_average('goals', season)
        season["assists"] = get_average('assists', season)
        season["points"] = get_average('points', season)
        season["powerPlayPoints"] = get_average('powerPlayPoints',
                                                       season)
        season["shorthandedPoints"] = get_average('shorthandedPoints',
                                                         season)
        season["plusMinus"] = get_average('plusMinus', season)
        season["shots"] = get_average('shots', season)
        season["pim"] = get_average('pim', season)

    return nhl_regular_seasons_data


def get_average(stat, stats_tot_avg):
    return round(stats_tot_avg[stat] / stats_tot_avg["gamesPlayed"], 2)


def get_position_abbreviation(position_code):
    if position_code in WINGERS_POSITION_CODES:
        return position_code + WINGERS_POSITION_CODES[2]
    else:
        return position_code


def inches_to_feet(height):
    feet, inches = divmod(height, INCH_TO_FEET_COEFFICIENT)
    return f"{feet}'{inches}\""


def format_season(season):
    return f'{season[:4]}-{season[6:]}'
