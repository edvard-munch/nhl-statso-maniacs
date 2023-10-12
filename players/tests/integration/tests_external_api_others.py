from players.management.commands import (upd_gms, upd_pls_proj, upd_pls_sbs,
                                         upd_pls_tot, upd_tms)

import pytest


def test_keys_response_get_schedule():
    mocked_keys = ['date', 'totalItems', 'totalEvents', 'totalGames',
                   'totalMatches', 'games', 'events', 'matches']
    mocked_keys_game = ['gamePk', 'link', 'gameType', 'season', 'gameDate',
                        'status', 'teams', 'venue', 'content']

    real_response = upd_gms.get_schedule()
    real_keys = list(real_response[0].keys())
    real_keys_game = list(real_response[0]['games'][0].keys())

    assert mocked_keys == real_keys

    assert mocked_keys_game == real_keys_game


@pytest.mark.parametrize('report_type, mocked_keys', [
    ['boxscore', ['copyright', 'teams', 'officials', 'team', 'teamStats',
                  'players', 'goalies', 'skaters', 'onIce', 'onIcePlus',
                  'scratches', 'penaltyBox', 'coaches']],
    ['linescore', ['copyright', 'currentPeriod', 'currentPeriodOrdinal',
                   'currentPeriodTimeRemaining', 'periods', 'shootoutInfo',
                   'teams', 'powerPlayStrength', 'hasShootout',
                   'intermissionInfo', 'powerPlayInfo', 'team', 'goals',
                   'shotsOnGoal', 'goaliePulled', 'numSkaters', 'powerPlay']]
])
def test_keys_response_gamedata(report_type, mocked_keys):
    url = 'http://statsapi.web.nhl.com/api/v1/game/{}/' + report_type
    game_id = 2019020001

    response = upd_gms.game_data(game_id, url)
    real_keys = list(response.keys()) + list(response['teams']['home'].keys())

    assert mocked_keys == real_keys


@pytest.mark.parametrize('function_name', [
    upd_pls_tot.player_ind_stats,
    upd_pls_sbs.player_ind_stats,
    upd_pls_proj.player_ind_stats,
])
def test_keys_response_player_endpoint(function_name):
    # it could be not working if player with the given id is not
    # played in the season yet
    mocked_keys = ['id', 'fullName', 'link', 'firstName', 'lastName', 'primaryNumber',
                   'birthDate', 'currentAge', 'birthCity', 'birthStateProvince',
                   'birthCountry', 'nationality', 'height', 'weight', 'active',
                   'alternateCaptain', 'captain', 'rookie', 'shootsCatches',
                   'rosterStatus', 'currentTeam', 'primaryPosition', 'stats']
    nhl_id = 8478402
    response = function_name(nhl_id).json()
    real_keys = list(response['people'][0].keys())

    assert mocked_keys == real_keys


def test_keys_response_teams():
    mocked_keys = ['id', 'name', 'link', 'venue', 'abbreviation', 'teamName',
                   'locationName', 'firstYearOfPlay', 'division', 'conference',
                   'franchise', 'shortName', 'officialSiteUrl', 'franchiseId',
                   'active']
    real_keys = list(upd_tms.get_response()[0].keys())

    assert mocked_keys == real_keys
