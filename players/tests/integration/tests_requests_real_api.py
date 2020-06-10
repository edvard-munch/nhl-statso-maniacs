from players.management.commands import upd_pls

START_FROM_INDEX = 0


def real_api_response(rep_type, pl_type, start_from_index):
    response = upd_pls.get_response(rep_type, pl_type, start_from_index).json()
    return response['data'][0]


def test_keys_response_goalies_bios():
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

    rep_type = 'bios'
    pl_type = 'goalie'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)

    assert real_response.keys() == mock_response.keys()


def test_keys_response_goalies_summary():
    mock_response = {
        'assists': 0,
        'gamesPlayed': 24,
        'gamesStarted': 21,
        'goalieFullName': 'Jake Allen',
        'goals': 0,
        'goalsAgainst': 48,
        'goalsAgainstAverage': 2.15075,
        'lastName': 'Allen',
        'losses': 6,
        'otLosses': 3,
        'penaltyMinutes': 0,
        'playerId': 8474596,
        'points': 0,
        'savePct': 0.92671,
        'saves': 607,
        'seasonId': 20192020,
        'shootsCatches': 'L',
        'shotsAgainst': 655,
        'shutouts': 2,
        'teamAbbrevs': 'STL',
        'ties': None,
        'timeOnIce': 80344,
        'wins': 12
    }

    rep_type = 'summary'
    pl_type = 'goalie'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)

    assert real_response.keys() == mock_response.keys()


def test_keys_response_skaters_bios():
    mock_response = {
        'assists': 3,
        'birthCity': 'Muskegon',
        'birthCountryCode': 'USA',
        'birthDate': '1987-02-25',
        'birthStateProvinceCode': 'MI',
        'currentTeamAbbrev': 'DET',
        'currentTeamName': 'Detroit Red Wings',
        'draftOverall': 42,
        'draftRound': 2,
        'draftYear': 2005,
        'firstSeasonForGameType': 20072008,
        'gamesPlayed': 49,
        'goals': 0,
        'height': 74,
        'isInHallOfFameYn': 'N',
        'lastName': 'Abdelkader',
        'nationalityCode': 'USA',
        'playerId': 8471716,
        'points': 3,
        'positionCode': 'L',
        'shootsCatches': 'L',
        'skaterFullName': 'Justin Abdelkader',
        'weight': 213
    }

    rep_type = 'bios'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)

    assert real_response.keys() == mock_response.keys()


def test_keys_response_skaters_summary():
    mock_response = {
        'assists': 3,
        'evGoals': 0,
        'evPoints': 3,
        'faceoffWinPct': 0.55072,
        'gameWinningGoals': 0,
        'gamesPlayed': 49,
        'goals': 0,
        'lastName': 'Abdelkader',
        'otGoals': 0,
        'penaltyMinutes': 25,
        'playerId': 8471716,
        'plusMinus': -14,
        'points': 3,
        'pointsPerGame': 0.06122,
        'positionCode': 'L',
        'ppGoals': 0,
        'ppPoints': 0,
        'seasonId': 20192020,
        'shGoals': 0,
        'shPoints': 0,
        'shootingPct': 0.0,
        'shootsCatches': 'L',
        'shots': 40,
        'skaterFullName': 'Justin Abdelkader',
        'teamAbbrevs': 'DET',
        'timeOnIcePerGame': 692.0204
    }

    rep_type = 'summary'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)

    assert real_response.keys() == mock_response.keys()


def test_keys_response_skaters_realtime():
    mock_response = {
        'blockedShots': 26,
        'blockedShotsPer60': 2.76,
        'emptyNetAssists': 0,
        'emptyNetGoals': 0,
        'emptyNetPoints': 0,
        'firstGoals': 0,
        'gamesPlayed': 49,
        'giveaways': 18,
        'giveawaysPer60': 1.91,
        'hits': 103,
        'hitsPer60': 10.93,
        'lastName': 'Abdelkader',
        'missedShotCrossbar': 0,
        'missedShotGoalpost': 1,
        'missedShotOverNet': 2,
        'missedShotWideOfNet': 18,
        'missedShots': 21,
        'otGoals': 0,
        'playerId': 8471716,
        'positionCode': 'L',
        'seasonId': 20192020,
        'shootsCatches': 'L',
        'skaterFullName': 'Justin Abdelkader',
        'takeaways': 10,
        'takeawaysPer60': 1.06,
        'teamAbbrevs': 'DET',
        'timeOnIcePerGame': 692.02
    }

    rep_type = 'realtime'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)

    assert real_response.keys() == mock_response.keys()


def test_keys_response_skaters_timeonice():
    mock_response = {
        'evTimeOnIce': 29060,
        'evTimeOnIcePerGame': 593.06122,
        'gamesPlayed': 49,
        'lastName': 'Abdelkader',
        'otTimeOnIce': 0,
        'otTimeOnIcePerOtGame': 0.0,
        'playerId': 8471716,
        'positionCode': 'L',
        'ppTimeOnIce': 1428,
        'ppTimeOnIcePerGame': 29.14285,
        'seasonId': 20192020,
        'shTimeOnIce': 3421,
        'shTimeOnIcePerGame': 69.81632,
        'shifts': 769,
        'shiftsPerGame': 15.69387,
        'shootsCatches': 'L',
        'skaterFullName': 'Justin Abdelkader',
        'teamAbbrevs': 'DET',
        'timeOnIce': 33909,
        'timeOnIcePerGame': 692.0204,
        'timeOnIcePerShift': 44.09492
    }

    rep_type = 'timeonice'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)

    assert real_response.keys() == mock_response.keys()
