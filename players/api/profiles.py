"""Typed public profiles and season history from explicitly separated saved data."""

import logging

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound

from players.models import Goalie, Skater, Team
from players.season_stats import (
    COMBINED_TEAM_PATTERN,
    GOALIE,
    NHL_LEAGUE,
    REGULAR_SEASON,
    SKATER,
    SKATER_COUNT_FIELDS,
    GOALIE_COUNT_FIELDS,
    normalize_season_id,
    read_season_stats,
)
from .catalogue import (
    AVERAGES,
    TOTALS,
    IDENTITY_FIELDS,
    SKATER_COUNTS,
    GOALIE_COUNTS,
    GOALIE_RATES,
    MAX_SAVE_PERCENTAGE,
    SKATER_TOTALS_KIND,
    SKATER_AVERAGES_KIND,
    GOALIE_TOTALS_KIND,
    number,
    public_identity,
    statistics,
)

from .game_detail import duration

logger = logging.getLogger(__name__)
MAX_PLAYER_NHL_ID = 2**31 - 1
PROFILE_FIELDS = (
    "first_name",
    "birth_city",
    "birth_state",
    "birth_country",
    "birth_country_abbr",
    "draft_round",
    "pl_number",
    "nhl_debut",
    "roster_status",
    "captain",
    "alt_captain",
    "relevant_video",
)
CAREER_TIMES = {
    "avg_toi_seconds": "avgToi",
    "avg_pp_toi_seconds": "powerPlayTimeOnIcePerGame",
    "avg_sh_toi_seconds": "shortHandedTimeOnIcePerGame",
}


def player_model(player_type):
    if player_type not in (SKATER, GOALIE):
        raise NotFound()
    return Goalie if player_type == GOALIE else Skater


def get_player(player_type, nhl_id, *, resource):
    model = player_model(player_type)
    if not 0 < nhl_id <= MAX_PLAYER_NHL_ID:
        raise NotFound()
    fields = ("nhl_id", "name", "last_name", "slug", "position_abbr", "gamelog_stats")
    queryset = model.objects
    if resource != "gamelog":
        fields = (*IDENTITY_FIELDS, "sbs_stats")
    if resource == "profile":
        fields = (*fields, *PROFILE_FIELDS, "team", "career_stats")
        if player_type == SKATER:
            fields += ("career_stats_avg",)
        queryset = queryset.select_related("team")
    return get_object_or_404(queryset.only(*fields), nhl_id=nhl_id)


def packet(stats, availability=None):
    if availability is None:
        availability = "partial" if any(value is None for value in stats.values()) else "complete"
    return {"availability": availability, "stats": stats}


def tagged(stats, player_type, mode):
    kind = (
        GOALIE_TOTALS_KIND
        if player_type == GOALIE
        else SKATER_AVERAGES_KIND
        if mode == AVERAGES
        else SKATER_TOTALS_KIND
    )
    return {**stats, "kind": kind}


def season_packet(rows, season, player_type, mode, *, team_abbr=None):
    if season is None:
        return packet(None, "missing")
    try:
        source = read_season_stats(rows, season, player_type=player_type, team_abbr=team_abbr)
        if source is None:
            return packet(None, "missing")
        return packet(tagged(statistics(source, player_type, mode), player_type, mode))
    except (ValueError, OverflowError):
        logger.warning("Unverified saved season statistics for %s season %s", player_type, season)
        return packet(None, "unverified")


def career_packet(raw, player_type, mode):
    if not isinstance(raw, dict) or not raw:
        return packet(None, "missing")
    result = {"games": number(raw.get("gamesPlayed"), integer=True)}
    if player_type == SKATER:
        for target, source in SKATER_COUNTS.items():
            result[target] = number(
                raw.get(SKATER_COUNT_FIELDS[source]),
                signed=target == "plus_minus",
                integer=mode == TOTALS,
            )
        result.update(
            {target: duration(raw.get(source)) for target, source in CAREER_TIMES.items()}
        )
    else:
        result.update(
            {
                target: number(raw.get(GOALIE_COUNT_FIELDS[source]), integer=True)
                for target, source in GOALIE_COUNTS.items()
            }
        )
        result.update(
            {
                target: number(
                    raw.get("goalsAgainstAvg" if target == "goals_against_average" else "savePctg")
                )
                for target in GOALIE_RATES
            }
        )
        if result["saves"] is None:
            shots, goals = (
                number(raw.get("shotsAgainst"), integer=True),
                number(raw.get("goalsAgainst"), integer=True),
            )
            if shots is not None and goals is not None and shots >= goals:
                result["saves"] = shots - goals
        if (
            result["save_percentage"] is not None
            and result["save_percentage"] > MAX_SAVE_PERCENTAGE
        ):
            result["save_percentage"] = None
    return packet(tagged(result, player_type, mode))


def profile(player, player_type, season, mode):
    identity = public_identity(player)
    identity.update({field: getattr(player, field) for field in PROFILE_FIELDS})
    identity["player_type"] = player_type
    return {
        "player": identity,
        "current_team": player.team,
        "selected_season": season_packet(player.sbs_stats, season, player_type, mode),
        "career_totals": career_packet(player.career_stats, player_type, TOTALS),
        "career_averages": career_packet(player.career_stats_avg, player_type, AVERAGES)
        if player_type == SKATER
        else None,
        "meta": {"season_id": season, "mode": mode, "player_type": player_type},
    }


def history(player, player_type, mode):
    rows = player.sbs_stats if isinstance(player.sbs_stats, list) else []
    seasons = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("leagueAbbrev", NHL_LEAGUE) != NHL_LEAGUE
            or row.get("gameTypeId", REGULAR_SEASON) != REGULAR_SEASON
        ):
            continue
        try:
            season = normalize_season_id(row.get("season"))
        except ValueError:
            continue
        teams = seasons.setdefault(season, set())
        abbr = row.get("teamAbbr")
        if isinstance(abbr, str) and abbr and not COMBINED_TEAM_PATTERN.fullmatch(abbr):
            teams.add(abbr)
    team_names = (
        {team.abbr: team for team in Team.objects.only("nhl_id", "abbr", "name", "slug")}
        if seasons
        else {}
    )
    result = []
    for season in sorted(seasons, reverse=True):
        contributions = []
        for abbr in sorted(seasons[season]):
            team = team_names.get(abbr)
            contributions.append(
                {
                    "team": {
                        "abbr": abbr,
                        "nhl_id": team.nhl_id if team else None,
                        "name": team.name if team else abbr,
                        "slug": team.slug if team else None,
                    },
                    **season_packet(rows, season, player_type, mode, team_abbr=abbr),
                }
            )
        result.append(
            {
                "season_id": season,
                **season_packet(rows, season, player_type, mode),
                "contributions": contributions,
            }
        )
    return result
