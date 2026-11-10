"""Common owned-list projections; callers hold the account lock through serialization."""

from rest_framework.exceptions import NotFound

from players.models import Team
from players.season_stats import SKATER
from .catalogue import (
    IDENTITY_FIELDS,
    DEFAULT_ORDERING,
    AVERAGES,
    matches,
    ordered_rows,
    participating_teams,
    public_identity,
    resolve_season,
)
from .profiles import MAX_PLAYER_NHL_ID, player_model, season_packet, career_packet

SEASON = "season"
CAREER = "career"


def saved_rows(owner, query, relation, *, scope=SEASON):
    season = resolve_season(query) if scope == SEASON else None
    player_type, mode = query["player_type"], query["mode"]
    ordering = query.get("ordering", DEFAULT_ORDERING[player_type])
    teams = (
        {team.abbr: team for team in Team.objects.only("nhl_id", "abbr", "name", "slug")}
        if season
        else {}
    )
    source_field = (
        "sbs_stats"
        if scope == SEASON
        else "career_stats_avg"
        if player_type == SKATER and mode == AVERAGES
        else "career_stats"
    )
    candidates = getattr(owner, relation).only(*IDENTITY_FIELDS, source_field)
    rows = []
    for player in candidates:
        source = getattr(player, source_field)
        saved = (
            season_packet(source, season, player_type, mode)
            if scope == SEASON
            else career_packet(source, player_type, mode)
        )
        row = {
            **public_identity(player),
            "player_type": player_type,
            **saved,
            "teams": participating_teams(source, season, teams)
            if scope == SEASON and saved["stats"] is not None
            else [],
        }
        if matches(row, query):
            rows.append(row)
    return ordered_rows(rows, ordering), {
        "season_id": season,
        "player_type": player_type,
        "mode": mode,
        "ordering": ordering,
    }


def membership_target(player_type, nhl_id):
    model = player_model(player_type)
    if not 0 < nhl_id <= MAX_PLAYER_NHL_ID:
        raise NotFound()
    return model
