"""Public season catalogue projections; no HTML, private state or upstream I/O."""

import logging
import math
import re

from players.models import Goalie, Skater, Team
from players.season_stats import (
    COMBINED_TEAM_PATTERN,
    GOALIE,
    NHL_LEAGUE,
    REGULAR_SEASON,
    SKATER,
    normalize_season_id,
    read_season_stats,
)
from players.seasons import available_seasons

logger = logging.getLogger(__name__)
TOTALS = "totals"
AVERAGES = "averages"
SECONDS_PER_MINUTE = 60
MAX_SAVE_PERCENTAGE = 1
SKATER_TOTALS_KIND = "skater_totals"
SKATER_AVERAGES_KIND = "skater_averages"
GOALIE_TOTALS_KIND = "goalie_totals"
DURATION = re.compile(r"([0-9]+):([0-5][0-9])")
IDENTITY_FIELDS = (
    "nhl_id",
    "name",
    "last_name",
    "slug",
    "image",
    "nation_flag",
    "position_abbr",
    "position_name",
    "nation",
    "nation_abbr",
    "age",
    "birth_date",
    "weight",
    "height_cm",
    "weight_kg",
    "draft_year",
    "draft_number",
    "rookie",
)
BIO_NUMBERS = ("age", "height_cm", "weight_kg", "weight_lb", "draft_year", "draft_number")
SKATER_COUNTS = {
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "plus_minus": "plus_minus",
    "penalty_minutes": "penalty_min",
    "shots_on_goal": "shots",
    "hits": "hits",
    "blocked_shots": "blocks",
    "faceoffs_won": "faceoff_wins",
    "pp_points": "pp_points",
    "sh_points": "sh_points",
}
SKATER_TIMES = {
    "avg_toi_seconds": "time_on_ice",
    "avg_pp_toi_seconds": "time_on_ice_pp",
    "avg_sh_toi_seconds": "time_on_ice_sh",
}
GOALIE_COUNTS = {
    "wins": "wins",
    "losses": "losses",
    "ot_losses": "ot_losses",
    "saves": "saves",
    "shutouts": "shotouts",
}
GOALIE_RATES = {"goals_against_average": "goals_against_av", "save_percentage": "saves_perc"}
COMMON_NUMBERS = frozenset({"games", *BIO_NUMBERS})
SKATER_NUMBERS = frozenset({*COMMON_NUMBERS, *SKATER_COUNTS, *SKATER_TIMES})
GOALIE_NUMBERS = frozenset({*COMMON_NUMBERS, *GOALIE_COUNTS, *GOALIE_RATES})
ALL_NUMBERS = SKATER_NUMBERS | GOALIE_NUMBERS
STAT_NUMBERS = ALL_NUMBERS - set(BIO_NUMBERS)
ORDERING_IDENTITIES = frozenset(
    {"name", "last_name", "nhl_id", "position_abbr", "nation_abbr", "birth_date"}
)
DEFAULT_ORDERING = {SKATER: "-points,last_name,nhl_id", GOALIE: "-wins,last_name,nhl_id"}


def number(value, *, signed=False, integer=False):
    if type(value) not in (int, float):
        return None
    try:
        if not math.isfinite(value):
            return None
    except OverflowError:
        return None
    if not signed and value < 0:
        return None
    if integer:
        return int(value) if value == int(value) else None
    return value


def duration(value):
    match = DURATION.fullmatch(value) if isinstance(value, str) else None
    return int(match[1]) * SECONDS_PER_MINUTE + int(match[2]) if match else None


def statistics(stats, player_type, mode):
    totals = stats.totals
    result = {"games": number(totals["games"], integer=True)}
    if player_type == SKATER:
        for target, source in SKATER_COUNTS.items():
            total = number(totals[source], signed=target == "plus_minus", integer=True)
            result[target] = total
            if mode == AVERAGES:
                result[target] = (
                    number(stats.averages[source + "_avg"], signed=target == "plus_minus")
                    if total is not None
                    else None
                )
        result.update({target: duration(totals[source]) for target, source in SKATER_TIMES.items()})
    else:
        result.update(
            {
                target: number(totals[source], integer=True)
                for target, source in GOALIE_COUNTS.items()
            }
        )
        result.update({target: number(totals[source]) for target, source in GOALIE_RATES.items()})
        if (
            result["save_percentage"] is not None
            and result["save_percentage"] > MAX_SAVE_PERCENTAGE
        ):
            result["save_percentage"] = None
    return result


def resolve_season(query):
    if "season_id" in query:
        return query["season_id"]
    seasons = available_seasons()
    return seasons[0] if seasons else None


def catalogue(query, *, team=None):
    season = resolve_season(query)
    player_type, mode = query["player_type"], query["mode"]
    ordering = query.get("ordering", DEFAULT_ORDERING[player_type])
    meta = {"season_id": season, "player_type": player_type, "mode": mode, "ordering": ordering}
    if season is None or (
        team is not None and (not team.abbr or COMBINED_TEAM_PATTERN.fullmatch(team.abbr))
    ):
        return [], meta
    teams = (
        {team.abbr: team}
        if team is not None
        else {item.abbr: item for item in Team.objects.only("nhl_id", "name", "abbr", "slug")}
    )
    model = Goalie if player_type == GOALIE else Skater
    rows = []
    candidates = model.objects.all()
    extra_fields = ()
    if team is not None:
        candidates = candidates.filter(sbs_stats__contains=[{"teamAbbr": team.abbr}])
        extra_fields = ("pl_number",)
    for player in candidates.only(*IDENTITY_FIELDS, "sbs_stats", *extra_fields).iterator():
        try:
            stats = read_season_stats(
                player.sbs_stats,
                season,
                player_type=player_type,
                team_abbr=team.abbr if team is not None else None,
            )
        except (ValueError, OverflowError):
            logger.warning(
                "Skipping invalid season statistics for %s %s", player_type, player.nhl_id
            )
            continue
        if stats is None:
            continue
        projected = statistics(stats, player_type, mode)
        if projected["games"] is None or projected["games"] <= 0:
            continue
        row = public_identity(player)
        row.update(
            _player=player,
            player_type=player_type,
            teams=participating_teams(player.sbs_stats, season, teams, team=team),
            stats=projected,
            availability="partial"
            if any(value is None for value in projected.values())
            else "complete",
        )
        if matches(row, query):
            rows.append(row)
    return ordered_rows(rows, ordering), meta


def ordered_rows(rows, ordering):
    # Identity tie-breakers do not depend on database insertion order.
    rows.sort(key=lambda row: (row["last_name"].casefold(), row["nhl_id"]))
    for term in reversed(ordering.split(",")):
        field, descending = term.lstrip("-"), term.startswith("-")
        known = [row for row in rows if value(row, field) is not None]
        unknown = [row for row in rows if value(row, field) is None]
        rows = (
            sorted(known, key=lambda row: sort_value(value(row, field)), reverse=descending)
            + unknown
        )
    return rows


def value(row, field):
    return (row["stats"] or {}).get(field) if field in STAT_NUMBERS else row.get(field)


def sort_value(value):
    return value.casefold() if isinstance(value, str) else value


def matches(row, query):
    if query.get("search") and query["search"].casefold() not in row["name"].casefold():
        return False
    for key, field in (("position", "position_abbr"), ("nation", "nation_abbr")):
        if key in query and row[field] not in query[key]:
            return False
    if "team" in query and not any(team["abbr"] in query["team"] for team in row["teams"]):
        return False
    if "rookie" in query and row["rookie"] != query["rookie"]:
        return False
    for suffix in ("min", "max"):
        key = "birth_date_" + suffix
        if key in query and (
            row["birth_date"] < query[key] if suffix == "min" else row["birth_date"] > query[key]
        ):
            return False
    for field in ALL_NUMBERS:
        null_key = field + "_isnull"
        if null_key in query and (value(row, field) is None) != query[null_key]:
            return False
        for suffix in ("min", "max"):
            key = field + "_" + suffix
            if key not in query:
                continue
            actual = value(row, field)
            if actual is None or (actual < query[key] if suffix == "min" else actual > query[key]):
                return False
    return True


def public_identity(player):
    row = {
        field: getattr(player, field)
        for field in IDENTITY_FIELDS
        if field not in ("image", "nation_flag")
    }
    row["weight_lb"] = row.pop("weight")
    row.update({field: number(row[field]) for field in BIO_NUMBERS})
    return {**row, "_player": player}


def participating_teams(rows, season, teams, *, team=None):
    """Metadata for rows already validated by the season reader."""
    participation = set()
    for row in rows:
        try:
            row_season = normalize_season_id(row.get("season"))
        except ValueError:
            continue
        abbr = row.get("teamAbbr")
        if (
            row_season == season
            and row.get("leagueAbbrev", NHL_LEAGUE) == NHL_LEAGUE
            and row.get("gameTypeId", REGULAR_SEASON) == REGULAR_SEASON
            and isinstance(abbr, str)
            and abbr
            and (team is None or abbr == team.abbr)
            and not COMBINED_TEAM_PATTERN.fullmatch(abbr)
        ):
            participation.add(abbr)
    return [
        {
            "abbr": abbr,
            "name": teams[abbr].name if abbr in teams else abbr,
            "nhl_id": teams[abbr].nhl_id if abbr in teams else None,
            "slug": teams[abbr].slug if abbr in teams else None,
        }
        for abbr in sorted(participation)
    ]
