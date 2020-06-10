from django.core import serializers
from players import models
from django.core.management.base import BaseCommand


MODELS = {
    'team': models.Team,
    'goalie': models.Goalie,
    'skater': models.Skater,
    'games': models.Game,
    'gameday': models.Gameday,
    'gameside': models.Side,
}
OBJECTS_NUMBER = 10


class Command(BaseCommand):
    """ """
    help = 'Creating JSON fixtures for tests'

    def handle(self, *args, **options):
        for key, value in MODELS.items():
            if key == 'team':
                data = serializers.serialize('json', value.objects.all(), indent=2)
            else:
                data = serializers.serialize('json', value.objects.all()[:OBJECTS_NUMBER], indent=2)
            with open(f'players/fixtures/{key}_objects.json', 'w') as file:
                file.write(data)
