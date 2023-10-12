import requests_mock
from furl import furl
from players.management.commands import upd_pls


# @requests_mock.Mocker()
def test_get_response_goalies_bios(requests_mock):
    rep_type = 'bios'
    pl_type = 'goalie'
    start_from_index = 0
    url = f'https://api.nhle.com/stats/rest/en/{pl_type}/{rep_type}'
    params = {
        'isAggregate': 'false',
        'isGame': 'false',
        'limit': 100,
        'start': 0,
        'cayenneExp': 'gameTypeId=2 and seasonId=20192020',
        'sort': '[{"property":"lastName","direction":"ASC_CI"}, {"property":"playerId","direction":"ASC_CI"}]',
    }
    url = str(furl(url).add(params))

    mock_response = {
        'birthCity': 'Fredericton',
        'birthCountryCode': 'CAN',
        'birthDate': '1990-08-07',
        'birthStateProvinceCode': 'NB',
        'currentTeamAbbrev': 'STL',
        'draftOverall': 34,
        'draftRound': 2,
        'draftYear': 2008,
        'firstSeasonForGameType': 20122013,
        'gamesPlayed': 24,
        'goalieFullName': 'Jake Allen',
        'height': 74,
        'isInHallOfFameYn': 'N',
        'lastName': 'Allen',
        'losses': 6,
        'nationalityCode': 'CAN',
        'otLosses': 3,
        'playerId': 8474596,
        'shootsCatches': 'L',
        'shutouts': 2,
        'ties': None,
        'weight': 203,
        'wins': 12
    }

    requests_mock.get(url, json=mock_response)
    response = upd_pls.get_response(rep_type, pl_type, start_from_index).json()

    assert response == mock_response


def test_no_response_goalies_bios(requests_mock):
    rep_type = 'bios'
    pl_type = 'goalie'
    start_from_index = 0
    url = f'https://api.nhle.com/stats/rest/en/{pl_type}/{rep_type}'
    params = {
        'isAggregate': 'false',
        'isGame': 'false',
        'limit': 100,
        'start': 0,
        'cayenneExp': 'gameTypeId=2 and seasonId=20192020',
        'sort': '[{"property":"lastName","direction":"ASC_CI"}, {"property":"playerId","direction":"ASC_CI"}]',
    }
    url = str(furl(url).add(params))
    requests_mock.get(url, status_code=401)
    response = upd_pls.get_response(rep_type, pl_type, start_from_index)

    assert response.status_code == 401
