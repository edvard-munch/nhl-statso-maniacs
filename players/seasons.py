"""Loaded NHL regular-season discovery shared by legacy pages and JSON APIs."""

from .models import Goalie, Skater
from .season_stats import NHL_LEAGUE, REGULAR_SEASON, SEASON_SUFFIX_LENGTH, normalize_season_id

SEASON_START_YEAR_LENGTH = 4


def season_label(season_id):
    return (
        "{}-{}".format(season_id[:SEASON_START_YEAR_LENGTH], season_id[-SEASON_SUFFIX_LENGTH:])
        if season_id
        else None
    )


def available_seasons():
    seasons = set()
    for model in (Skater, Goalie):
        for rows in model.objects.values_list("sbs_stats", flat=True).iterator():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if (
                    row.get("leagueAbbrev", NHL_LEAGUE) != NHL_LEAGUE
                    or row.get("gameTypeId", REGULAR_SEASON) != REGULAR_SEASON
                ):
                    continue
                try:
                    seasons.add(normalize_season_id(row.get("season")))
                except ValueError:
                    continue
    return sorted(seasons, reverse=True)
