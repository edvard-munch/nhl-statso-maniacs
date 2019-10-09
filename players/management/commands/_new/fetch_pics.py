import requests
from django.core.management.base import BaseCommand, CommandError
from django.core.files import File
import urllib.request as urllib
from tqdm import tqdm

from players.models import Skater
from players.models import Goalie


URL_PICS = 'https://nhl.bamcontent.com/images/headshots/current/168x168/{}.jpg'


class Command(BaseCommand):
    """ """

    def handle(self, *args, **options):
        """

        Args:
          *args: 
          **options: 

        Returns:

        """
        g = Goalie.all().values_list('name', 'nhl_id')
        s = Skater.all().values_list('name', 'nhl_id')
        favorites = g.union(s)
        for item in favorites:
            content = urllib.urlretrieve(URL_PICS.format(item.nhl_id))
            pic = File(open(content[0], 'rb'))
            name_pattern = f'{item.slug}.jpg'
