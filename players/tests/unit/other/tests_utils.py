from django.core.management import call_command

from players import utils
from players.models import Goalie, Skater
from django.contrib.auth.models import User
from django.test import RequestFactory
import json
import os
import sys
from files import gamelog


import pytest
import re
from datetime import datetime


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', 'team_objects.json')
        call_command('loaddata', 'skater_objects.json')
        call_command('loaddata', 'goalie_objects.json')
        call_command('loaddata', 'user_objects.json')


@pytest.mark.django_db()
@pytest.mark.parametrize('queryset, field, result', [
    [Skater.objects.all(), 'height_cm', (178, 196)],
    [Skater.objects.all(), 'weight', (165, 213)],
    [Skater.objects.all(), 'age', (22, 30)],
    [Goalie.objects.all(), 'height_cm', (183, 198)],
    [Goalie.objects.all(), 'weight', (180, 240)],
    [Goalie.objects.all(), 'age', (23, 34)]
])
def test_get_range(queryset, field, result):
    assert utils.get_range(queryset, field) == result


@pytest.mark.django_db()
@pytest.mark.parametrize('players', [
    Skater.objects.all(),
    Goalie.objects.all(),
])
def test_adjust_measurements(players):
    player = players.first()
    player_adjusted = utils.adjust_measurements(player)

    assert player.weight_kg == player_adjusted.weight

    assert player.weight_kg == player_adjusted.weight


@pytest.mark.django_db()
def test_measurements_format_is_euro():
    user = User.objects.first()
    user.profile.measurements_format = 'Europe'

    assert utils.measurements_format_is_euro(user)

    user.profile.measurements_format = 'USA'

    assert not utils.measurements_format_is_euro(user)


# working with testserver instead of a real domain, because of RequestsFactory
def test_anon_alert():
    factory = RequestFactory()
    request = factory.get('/player/leon-draisaitl/8477934/player_compare/')
    input_ = 'http://testserver/player/leon-draisaitl/8477934/'
    expected = 'You are not authenticated. <a href="//testserver/register/">Register</a> or <a href="//testserver/login/?next=http://testserver/player/leon-draisaitl/8477934/">Login</a>'
    assert utils.anon_alert(request, input_) == expected


@pytest.mark.parametrize('string, result', [
    ['page=3', 3],
    ['size=50', 50],
])
def test_parse_url_param(string, result):
    assert utils.parse_url_param(string) == result


# file_path = os.path.join(sys.path[0], 'gamelog.json')
# games = None
# with open(file_path) as file:
#     games = json.load(file)
#     print(games)

# print(type(games))
# filtered_games = None
# file_path_filtered = os.path.join(sys.path[0], 'filtered_gamelog.txt')
# print()
# with open(file_path_filtered) as file:
#     filtered_games = file

columns_skaters = ['player.name', 'team.abbr', 'format_date', 'opponent.abbr',
                   'goals', 'assists', 'points', 'plusMinus', 'penaltyMinutes',
                   'shots', 'hits', 'blocked', 'faceOffWins', 'powerPlayPoints',
                   'shortHandedPoints', 'timeOnIce', 'powerPlayTimeOnIce',
                   'shortHandedTimeOnIce']

columns_goalies = ['player.name', 'team.abbr', 'format_date', 'opponent.abbr',
                   'decision', 'timeOnIce', 'goalsAgainst', 'savePercentage',
                   'saves', 'shots', 'shutout']


@pytest.mark.parametrize('games, filtering, columns, filtered_games', [
    [gamelog.GAMES_SKATERS, [['0', 'fou']], columns_skaters, gamelog.FILTERED_GAMES_OPTION_ONE],
    [gamelog.GAMES_SKATERS, [['1', 'tor']], columns_skaters, gamelog.FILTERED_GAMES_OPTION_TWO],
    [gamelog.GAMES_GOALIES, [['0', 'wer']], columns_goalies, gamelog.FILTERED_GAMES_OPTION_THREE],
    [gamelog.GAMES_SKATERS, [['0', 'kor'], ['1', 'cbj']], columns_skaters, []],
    [gamelog.GAMES_SKATERS, [['0', 'br'], ['1', 'vgk']], columns_skaters, gamelog.FILTERED_GAMES_OPTION_FOUR],
])
def test_filter_gamelog(games, filtering, columns, filtered_games):
    assert utils.filter_gamelog(games, filtering, columns) == filtered_games


# do something with this html values
positions_html = '<label for="C" class="position_checkboxradio_skt cell-with-tooltip">C <span class="css-tooltip">Center</span></label><input type="checkbox" class="position_checkboxradio_skt checkbox_button" value="C" id="C"> &nbsp<label for="D" class="position_checkboxradio_skt cell-with-tooltip">D <span class="css-tooltip">Defenseman</span></label><input type="checkbox" class="position_checkboxradio_skt checkbox_button" value="D" id="D"> &nbsp<label for="LW" class="position_checkboxradio_skt cell-with-tooltip">LW <span class="css-tooltip">Left Wing</span></label><input type="checkbox" class="position_checkboxradio_skt checkbox_button" value="LW" id="LW"> &nbsp<label for="RW" class="position_checkboxradio_skt cell-with-tooltip">RW <span class="css-tooltip">Right Wing</span></label><input type="checkbox" class="position_checkboxradio_skt checkbox_button" value="RW" id="RW"> &nbsp'
nations_html = '<label for="Australia" class="nation_checkboxradio_skt cell-with-tooltip">Australia </label><input type="checkbox" class="nation_checkboxradio_skt checkbox_button" value="Australia" id="Australia"> &nbsp<label for="Canada" class="nation_checkboxradio_skt cell-with-tooltip">Canada </label><input type="checkbox" class="nation_checkboxradio_skt checkbox_button" value="Canada" id="Canada"> &nbsp<label for="Czech Republic" class="nation_checkboxradio_skt cell-with-tooltip">Czech Republic </label><input type="checkbox" class="nation_checkboxradio_skt checkbox_button" value="Czech Republic" id="Czech Republic"> &nbsp<label for="Denmark" class="nation_checkboxradio_skt cell-with-tooltip">Denmark </label><input type="checkbox" class="nation_checkboxradio_skt checkbox_button" value="Denmark" id="Denmark"> &nbsp<label for="Finland" class="nation_checkboxradio_skt cell-with-tooltip">Finland </label><input type="checkbox" class="nation_checkboxradio_skt checkbox_button" value="Finland" id="Finland"> &nbsp'
teams_html = '<label for="OTT" class="team_checkboxradio_skt cell-with-tooltip">OTT <span class="css-tooltip">Ottawa Senators</span></label><input type="checkbox" class="team_checkboxradio_skt checkbox_button" value="OTT" id="OTT"> &nbsp<label for="PHI" class="team_checkboxradio_skt cell-with-tooltip">PHI <span class="css-tooltip">Philadelphia Flyers</span></label><input type="checkbox" class="team_checkboxradio_skt checkbox_button" value="PHI" id="PHI"> &nbsp<label for="PIT" class="team_checkboxradio_skt cell-with-tooltip">PIT <span class="css-tooltip">Pittsburgh Penguins</span></label><input type="checkbox" class="team_checkboxradio_skt checkbox_button" value="PIT" id="PIT"> &nbsp'


# test with checked values
@pytest.mark.parametrize('array, checkbox_class, kwargs, result', [
    [[('OTT', 'Ottawa Senators'), ('PHI', 'Philadelphia Flyers'),
      ('PIT', 'Pittsburgh Penguins')], 'team_checkboxradio_skt',
     {'tip': True}, teams_html],
    [[('Australia', None), ('Canada', None), ('Czech Republic', None),
      ('Denmark', None), ('Finland', None)], 'nation_checkboxradio_skt',
     {'tip': False}, nations_html],
    [[('C', 'Center'), ('D', 'Defenseman'), ('LW', 'Left Wing'),
      ('RW', 'Right Wing')], 'position_checkboxradio_skt', {'tip': True},
     positions_html],
])
def test_checkox(array, checkbox_class, kwargs, result):
    assert utils.checkbox(array, checkbox_class, **kwargs) == result


position_option_html = '<label for="RW" class="position_checkboxradio_skt cell-with-tooltip">RW <span class="css-tooltip">Right Wing</span></label><input type="checkbox" class="position_checkboxradio_skt checkbox_button" value="RW" id="RW"> &nbsp'
nation_option_html = '<label for="USA" class="nation_checkboxradio_skt cell-with-tooltip">USA </label><input type="checkbox" class="nation_checkboxradio_skt checkbox_button" value="USA" id="USA"> &nbsp'
team_option_html = '<label for="NYR" class="team_checkboxradio_skt cell-with-tooltip">NYR <span class="css-tooltip">New York Rangers</span></label><input type="checkbox" class="team_checkboxradio_skt checkbox_button" value="NYR" id="NYR"> &nbsp'


@pytest.mark.parametrize('option, checkbox_class, kwargs, result', [
    [('RW', 'Right Wing'), 'position_checkboxradio_skt',
     {'tip': True, 'check_this': False}, position_option_html],
    [('USA', None), 'nation_checkboxradio_skt',
     {'tip': False, 'check_this': False}, nation_option_html],
    [('NYR', 'New York Rangers'), 'team_checkboxradio_skt',
     {'tip': True, 'check_this': False}, team_option_html]
])
def test_checkox_option(option, checkbox_class, kwargs, result):
    assert utils.checkbox_option(option, checkbox_class, **kwargs) == result


# HOW TO TEST PROPERLY THAT IT CALCULATES A CORRECT DATE
def test_get_us_pacific_date():
    result = utils.get_us_pacific_date()
    date_regex = r"\d{4}-\d{2}-\d{2}"

    assert isinstance(result, str)

    assert re.match(date_regex, result)


@pytest.mark.parametrize('array, element, quantity, result', [
    [['1', '2', '3', '4', '5', '6'], '5', 3, ['4', '5', '6']],
    [['1', '2', '3', '4', '5', '6'], '2', 4, ['1', '2', '3', '4']],
    [['1', '2', '3', '4', '5', '6'], '6', 2, ['5', '6']],
    [['1', '2', '3', '4', '5', '6'], '1', 5, ['1', '2', '3', '4', '5']],
    [['1', '2', '3', '4', '5', '6'], '4', 4, ['2', '3', '4', '5']],
])
def test_get_adjacent(array, element, quantity, result):
    assert utils.get_adjacent(array, element, quantity) == result


@pytest.mark.parametrize('date_now, result', [
    ['2020-06-10', '2019-06-10'],
    ['2021-04-25', '2020-04-25'],
])
def test_get_default_date(date_now, result):
    date_now = datetime.strptime(date_now, '%Y-%m-%d')
    result = datetime.strptime(result, '%Y-%m-%d')

    assert utils.get_default_date(date_now) == result
