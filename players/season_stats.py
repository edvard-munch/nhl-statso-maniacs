"""Read regular-season NHL table statistics without accessing the ORM or API."""

import math
import re
from dataclasses import dataclass
from numbers import Real
from typing import Optional


SKATER = "skater"
GOALIE = "goalie"
NHL_LEAGUE = "NHL"
REGULAR_SEASON = 2
AVERAGE_PRECISION = 2
SAVE_PERCENTAGE_PRECISION = 3
SECONDS_PER_MINUTE = 60
SEASON_YEAR_SPAN = 1
SEASON_SUFFIX_LENGTH = 2
SEASON_ID_PATTERN = re.compile(r"^(\d{4})(\d{4})$")
SEASON_LABEL_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
TIME_PATTERN = re.compile(r"^(\d+):([0-5]\d)$")
COMBINED_TEAM_PATTERN = re.compile(r"^(TOT|(?:[2-9]|[1-9]\d+)TM)$")

SKATER_COUNT_FIELDS = {
    "games": "gamesPlayed",
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "plus_minus": "plusMinus",
    "penalty_min": "pim",
    "shots": "shots",
    "hits": "hits",
    "blocks": "blocked",
    "faceoff_wins": "faceoffsWon",
    "pp_points": "powerPlayPoints",
    "sh_points": "shorthandedPoints",
}
SKATER_TIME_FIELDS = {
    "time_on_ice": "avgToi",
    "time_on_ice_pp": "powerPlayTimeOnIce",
    "time_on_ice_sh": "shortHandedTimeOnIce",
}
GOALIE_COUNT_FIELDS = {
    "games": "gamesPlayed",
    "wins": "wins",
    "losses": "losses",
    "ot_losses": "otLosses",
    "saves": "saves",
    "shotouts": "shutouts",
}


@dataclass
class SeasonStatistics:
    season_id: str
    team_abbr: Optional[str]
    totals: dict
    averages: Optional[dict]


def normalize_season_id(season):
    """Accept an NHL season ID or a stored display label; reject ambiguous input."""
    value = str(season)
    match = SEASON_ID_PATTERN.fullmatch(value)
    if match:
        start_year, end_year = map(int, match.groups())
        if end_year == start_year + SEASON_YEAR_SPAN:
            return value
    match = SEASON_LABEL_PATTERN.fullmatch(value)
    if match:
        start_year = int(match.group(1))
        end_year = start_year + SEASON_YEAR_SPAN
        if str(end_year)[-SEASON_SUFFIX_LENGTH:] == match.group(2):
            return "{}{}".format(start_year, end_year)
    raise ValueError("Expected a consecutive season ID or label, e.g. 20262027 or 2026-27")


def read_season_stats(rows, season, *, player_type, team_abbr=None):
    """Return fresh table dictionaries for one season, or None when no row exists.

    Input is the player's sbs_stats array, never snapshot columns or sbs_stats_avg.
    A team filter selects that team's contributions. Without it, an explicit TOT
    or nTM row takes precedence over splits; otherwise distinct splits combine.
    Missing values propagate rather than producing partial totals or stale data.
    """
    season_id = normalize_season_id(season)
    if player_type not in (SKATER, GOALIE):
        raise ValueError("player_type must be 'skater' or 'goalie'")
    if team_abbr is not None and (
        not isinstance(team_abbr, str) or not team_abbr or _is_combined_team(team_abbr)
    ):
        raise ValueError("team_abbr must identify a single team")
    if not rows:
        return None
    if not isinstance(rows, list):
        raise ValueError("Season statistics must be a list of SBS rows")

    selected = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each SBS row must be a dictionary")
        if row.get("leagueAbbrev", NHL_LEAGUE) != NHL_LEAGUE:
            continue
        if row.get("gameTypeId", REGULAR_SEASON) != REGULAR_SEASON:
            continue
        try:
            row_season = normalize_season_id(row.get("season"))
        except ValueError:
            continue
        if row_season == season_id and (team_abbr is None or row.get("teamAbbr") == team_abbr):
            selected.append(row)
    if not selected:
        return None

    if team_abbr is None:
        combined = [row for row in selected if _is_combined_team(row.get("teamAbbr"))]
        if combined:
            selected = combined
    if len(selected) > 1:
        teams = [row.get("teamAbbr") for row in selected]
        if any(not team for team in teams) or len(set(teams)) != len(teams):
            raise ValueError("Multiple SBS rows require distinct team abbreviations")
        if any(_is_combined_team(team) for team in teams):
            raise ValueError("Multiple combined-season rows are ambiguous")

    if player_type == GOALIE:
        totals = _goalie_totals(selected)
        averages = None
    else:
        totals = {field: _sum_field(selected, key) for field, key in SKATER_COUNT_FIELDS.items()}
        totals.update(
            {field: _weighted_time(selected, key) for field, key in SKATER_TIME_FIELDS.items()}
        )
        averages = {
            field + "_avg": _per_game(totals[field], totals["games"])
            for field in SKATER_COUNT_FIELDS
            if field != "games"
        }
        averages["games"] = totals["games"]
        averages.update({field: totals[field] for field in SKATER_TIME_FIELDS})
    return SeasonStatistics(season_id, team_abbr, totals, averages)


def _is_combined_team(team):
    return isinstance(team, str) and COMBINED_TEAM_PATTERN.fullmatch(team) is not None


def _number(value):
    if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def _sum_field(rows, key):
    values = [_number(row.get(key)) for row in rows]
    return None if any(value is None for value in values) else sum(values)


def _per_game(value, games):
    if value is None or games is None or games <= 0:
        return None
    return round(value / games, AVERAGE_PRECISION)


def _time_seconds(value):
    match = TIME_PATTERN.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    minutes, seconds = map(int, match.groups())
    return minutes * SECONDS_PER_MINUTE + seconds


def _weighted_time(rows, key):
    games = _sum_field(rows, "gamesPlayed")
    if games is None or games <= 0:
        return None
    total_seconds = 0
    for row in rows:
        played = _number(row.get("gamesPlayed"))
        if played < 0:
            return None
        if played == 0:
            continue
        seconds = _time_seconds(row.get(key))
        if seconds is None:
            return None
        total_seconds += seconds * played
    minutes, seconds = divmod(round(total_seconds / games), SECONDS_PER_MINUTE)
    return "{:02d}:{:02d}".format(minutes, seconds)


def _goalie_totals(rows):
    # Saves can be absent in older stored rows; derive them without mutating JSON.
    prepared = []
    for row in rows:
        copy = dict(row)
        if _number(copy.get("saves")) is None:
            shots = _number(copy.get("shotsAgainst"))
            goals = _number(copy.get("goalsAgainst"))
            if shots is not None and goals is not None:
                copy["saves"] = shots - goals
        prepared.append(copy)
    totals = {field: _sum_field(prepared, key) for field, key in GOALIE_COUNT_FIELDS.items()}
    if len(rows) == 1:
        totals["goals_against_av"] = _number(rows[0].get("goalsAgainstAvg"))
        totals["saves_perc"] = _number(rows[0].get("savePctg"))
    else:
        # GAA requires actual goalie ice time, not games played as a weight.
        totals["goals_against_av"] = None
        shots = _sum_field(rows, "shotsAgainst")
        saves = totals["saves"]
        totals["saves_perc"] = (
            round(saves / shots, SAVE_PERCENTAGE_PRECISION)
            if saves is not None and shots is not None and shots > 0
            else None
        )
    return totals
