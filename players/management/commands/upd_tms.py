import os
import urllib

import requests
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

from players.models import Team

from . import upd_pls

URL_TEAMS = 'https://api-web.nhle.com/v1/schedule-calendar/now'
# URL_FRANCHISES = "https://api.nhle.com/stats/rest/en/franchise?sort=fullName&include=lastSeason.id&include=firstSeason.id"
URL_TEAMS_LOGOS = 'https://assets.nhle.com/logos/nhl/svg/{}_light.svg'
TEAMS_LOGOS_DIR = 'teams_logos'


class Command(BaseCommand):
    """ """

    def handle(self, *args, **options):
        """

        Args:
          *args: 
          **options: 

        Returns:

        """
        teams = get_response()

        for team in tqdm(teams):
            import_team(team)


def import_team(team):
    """

    Args:
      team:

    Returns:

    """
    nhl_id = team["id"]

    defaults = {
        'name': team["name"]["default"],
        'abbr': team["abbrev"],

        # 'arena_name': team[`"venue"]["name"],
        # 'arena_location': team["venue"]["city"],
        # 'division': team["division"]["name"],
        # 'conference': team["conference"]["name"],
        # 'off_site': team["officialSiteUrl"],
    }

    try:
        defaults['nhl_debut'] = team["firstYearOfPlay"] #in franchise
    except KeyError:
        pass

    team_obj = Team.objects.update_or_create(nhl_id=nhl_id, defaults=defaults)[0]
    img_name = f'{team_obj.slug}.svg'

    if upd_pls.pic_missing(img_name, team_obj.image, TEAMS_LOGOS_DIR):
        upd_pls.upload_pic(TEAMS_LOGOS_DIR, team_obj, img_name, URL_TEAMS_LOGOS)


def get_response():
    print('Uploading from teams report')
    try:
        return requests.get(URL_TEAMS).json()['teams']
    except requests.exceptions.ConnectionError as e:
        print(e)
        raise CommandError('CONNECTION COULD NOT BE ESTABLISHED. TRYING NEXT TASK')
