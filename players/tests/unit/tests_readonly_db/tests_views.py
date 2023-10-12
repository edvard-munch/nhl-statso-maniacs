"""
doesn't work with conftest in the same folder if load tests
from a parent folder
"""

from django.urls import reverse

import pytest


@pytest.mark.django_db()
@pytest.mark.parametrize('uri, args', [
    ['about', []],
    ['home', []],
    ['players', []],
    ['search', []],
    # ['ajax_calls/search/?term=ove', []], NO REVERSE MATCH
    ['favorites', []],
    ['teams', []],
    ['auth_callback', []],
    ['comparison', []],
    ['ajax_comparison_stat_switcher', ['skaters', 'season_tot']],
    ['ajax_comparison_stat_switcher', ['skaters', 'season_avg']],
    ['ajax_comparison_stat_switcher', ['skaters', 'career_tot']],
    ['ajax_comparison_stat_switcher', ['skaters', 'career_avg']],
    ['ajax_comparison_stat_switcher', ['goalies', 'career_tot']],
    ['ajax_comparison_stat_switcher', ['goalies', 'season_tot']],
    ['reset_comparison', ['goalies']],
    ['reset_comparison', ['skaters']],
    ['player_detail', ('jack-studnicka', 8480021)],
    ['player_detail', ('cory-schneider', 8471239)],
    ['player_gamelog', ('jack-studnicka', 8480021)],
    ['player_gamelog', ('cory-schneider', 8471239)],
    ['team_detail', ('calgary-flames', 20)],
    ['ajax_stats_switcher', ('calgary-flames', 20, 'avg', 't')],
    ['ajax_stats_switcher', ('calgary-flames', 20, 'avg', 'd')],
    ['ajax_stats_switcher', ('calgary-flames', 20, 'avg', 'f')],
    ['ajax_stats_switcher', ('calgary-flames', 20, 'tot', 't')],
    ['ajax_stats_switcher', ('calgary-flames', 20, 'tot', 'd')],
    ['ajax_stats_switcher', ('calgary-flames', 20, 'tot', 'f')],
    # it will work with any properly formatted date, because it replaces nonexistent
    # gamedays for last gameday object
    ['games', ('2019-09-01',)],
    ['game_detail', ('ottawa-senators-toronto-maple-leafs2019-10-02', 2019020001)],
    ['game_detail', ('detroit-red-wings-dallas-stars2020-01-03', 2019020640)],
    ['player_positions', ('jack-studnicka', 8480021)],
    ['player_positions', ('cory-schneider', 8471239)],
    ['player_note', ('jack-studnicka', 8480021)],
    ['player_note', ('cory-schneider', 8471239)],
    ['player_favorite', ('jack-studnicka', 8480021)],
    ['player_favorite', ('cory-schneider', 8471239)],
    ['player_compare', ('jack-studnicka', 8480021)],
    ['player_compare', ('cory-schneider', 8471239)],
    # # check for Anonymus - assert None
    ['ajax_fav_players_gamelog', ['skt_log', 'page=1', 'size=25', 'col', 'fcol']],
    ['ajax_fav_players_gamelog', ('skt_log', 'page=1', 'size=100', 'col', 'fcol')],
    ['ajax_fav_players_gamelog', ('gls_log', 'page=1', 'size=25', 'col', 'fcol')],
    ['ajax_players', ('gls', 'page=1', 'size=25', 'col', 'fcol', 'rookie_filter=',
                      'checkbox_filter=', 'fav_filt=True')],
    ['ajax_players', ('gls', 'page=1', 'size=25', 'col', 'fcol', 'rookie_filter=',
                      'checkbox_filter=')],
    ['ajax_players', ('tot', 'page=3', 'size=100', 'col', 'fcol', 'rookie_filter=',
                      'checkbox_filter=')],
    ['ajax_players', ('tot', 'page=2', 'size=25', 'col', 'fcol', 'rookie_filter=',
                      'checkbox_filter=', 'fav_filt=True')],
    ['ajax_players', ('avg', 'page=3', 'size=100', 'col', 'fcol', 'rookie_filter=',
                      'checkbox_filter=')],
    ['ajax_players', ('avg', 'page=2', 'size=25', 'col', 'fcol', 'rookie_filter=',
                      'checkbox_filter=', 'fav_filt=True')],
])
def test_views(uri, args, client, msg):
    print(msg)
    username = "arkadiy"
    password = "ark085075"
    # print(client.get(reverse(uri, args=args)))
    # print('---------------------')

    # print(username)
    client.login(username=username, password=password)

    if args:
        response = client.get(reverse(uri, args=args))
    else:
        response = client.get(reverse(uri))

    # assert response.context contains something
    assert response.status_code == 200
