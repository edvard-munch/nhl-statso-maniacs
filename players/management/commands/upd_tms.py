import os
import urllib

import requests
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

from players.models import Team

from . import upd_pls

URL_TEAMS = 'https://statsapi.web.nhl.com/api/v1/teams'
URL_TEAMS_LOGOS = 'https://www-league.nhlstatic.com/images/logos/teams-current-primary-light/{}.svg'
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
        print(f'\n Uploading from teams report')
        teams = requests.get(URL_TEAMS).json()["teams"]

        for team in tqdm(teams):
            self.import_team(team)

    def import_team(self, team):
        """

        Args:
          team: 

        Returns:

        """
        nhl_id = team["id"]

        defaults = {
            'name': team["name"],
            'abbr': team["abbreviation"],
            'arena_name': team["venue"]["name"],
            'arena_location': team["venue"]["city"],
            'division': team["division"]["name"],
            'conference': team["conference"]["name"],
            'off_site': team["officialSiteUrl"],
        }

        try:
            defaults['nhl_debut'] = team["firstYearOfPlay"]
        except KeyError:
            pass

        team_obj = Team.objects.update_or_create(nhl_id=nhl_id, defaults=defaults)[0]
        img_name = f'{team_obj.slug}.svg'

        if upd_pls.pic_missing(img_name, team_obj.image, TEAMS_LOGOS_DIR):
             upd_pls.upload_pic(TEAMS_LOGOS_DIR, team_obj, img_name, URL_TEAMS_LOGOS)
