from players.management.commands import upd_pls

START_FROM_INDEX = 0


def real_api_response(rep_type, pl_type, start_from_index):
    response = upd_pls.get_response(rep_type, pl_type, start_from_index).json()
    return response['data'][0]


def test_keys_response_goalies_bios():
    mocked_keys = ['birthCity', 'birthCountryCode', 'birthDate',
                   'birthStateProvinceCode', 'currentTeamAbbrev', 'draftOverall',
                   'draftRound', 'draftYear', 'firstSeasonForGameType',
                   'gamesPlayed', 'goalieFullName', 'height', 'isInHallOfFameYn',
                   'lastName', 'losses', 'nationalityCode', 'otLosses', 'playerId',
                   'shootsCatches', 'shutouts', 'ties', 'weight', 'wins']

    rep_type = 'bios'
    pl_type = 'goalie'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)
    real_keys = list(real_response.keys())

    assert mocked_keys == real_keys


def test_keys_response_goalies_summary():
    mocked_keys = ['assists', 'gamesPlayed', 'gamesStarted', 'goalieFullName',
                   'goals', 'goalsAgainst', 'goalsAgainstAverage', 'lastName',
                   'losses', 'otLosses', 'penaltyMinutes', 'playerId', 'points',
                   'savePct', 'saves', 'seasonId', 'shootsCatches', 'shotsAgainst',
                   'shutouts', 'teamAbbrevs', 'ties', 'timeOnIce', 'wins']

    rep_type = 'summary'
    pl_type = 'goalie'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)
    real_keys = list(real_response.keys())

    assert mocked_keys == real_keys


def test_keys_response_skaters_bios():
    mocked_keys = ['assists', 'birthCity', 'birthCountryCode', 'birthDate',
                   'birthStateProvinceCode', 'currentTeamAbbrev',
                   'currentTeamName', 'draftOverall', 'draftRound',
                   'draftYear', 'firstSeasonForGameType', 'gamesPlayed',
                   'goals', 'height', 'isInHallOfFameYn', 'lastName',
                   'nationalityCode', 'playerId', 'points', 'positionCode',
                   'shootsCatches', 'skaterFullName', 'weight']

    rep_type = 'bios'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)
    real_keys = list(real_response.keys())

    assert mocked_keys == real_keys


def test_keys_response_skaters_summary():
    mocked_keys = ['assists', 'evGoals', 'evPoints', 'faceoffWinPct',
                   'gameWinningGoals', 'gamesPlayed', 'goals', 'lastName',
                   'otGoals', 'penaltyMinutes', 'playerId', 'plusMinus',
                   'points', 'pointsPerGame', 'positionCode', 'ppGoals',
                   'ppPoints', 'seasonId', 'shGoals', 'shPoints', 'shootingPct',
                   'shootsCatches', 'shots', 'skaterFullName', 'teamAbbrevs',
                   'timeOnIcePerGame']

    rep_type = 'summary'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)
    real_keys = list(real_response.keys())

    assert mocked_keys == real_keys


def test_keys_response_skaters_realtime():
    mocked_keys = ['blockedShots', 'blockedShotsPer60', 'emptyNetAssists',
                   'emptyNetGoals', 'emptyNetPoints', 'firstGoals',
                   'gamesPlayed', 'giveaways', 'giveawaysPer60', 'hits',
                   'hitsPer60', 'lastName', 'missedShotCrossbar',
                   'missedShotGoalpost', 'missedShotOverNet',
                   'missedShotWideOfNet', 'missedShots', 'otGoals', 'playerId',
                   'positionCode', 'seasonId', 'shootsCatches', 'skaterFullName',
                   'takeaways', 'takeawaysPer60', 'teamAbbrevs', 'timeOnIcePerGame']

    rep_type = 'realtime'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)
    real_keys = list(real_response.keys())

    assert mocked_keys == real_keys


def test_keys_response_skaters_timeonice():
    mocked_keys = ['evTimeOnIce', 'evTimeOnIcePerGame', 'gamesPlayed',
                   'lastName', 'otTimeOnIce', 'otTimeOnIcePerOtGame',
                   'playerId', 'positionCode', 'ppTimeOnIce',
                   'ppTimeOnIcePerGame', 'seasonId', 'shTimeOnIce',
                   'shTimeOnIcePerGame', 'shifts', 'shiftsPerGame',
                   'shootsCatches', 'skaterFullName', 'teamAbbrevs',
                   'timeOnIce', 'timeOnIcePerGame', 'timeOnIcePerShift']

    rep_type = 'timeonice'
    pl_type = 'skater'
    real_response = real_api_response(rep_type, pl_type, START_FROM_INDEX)
    real_keys = list(real_response.keys())

    assert mocked_keys == real_keys
