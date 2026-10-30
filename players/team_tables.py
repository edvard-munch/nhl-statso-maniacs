"""Read-only team contributions for the selected regular season."""

import logging
from dataclasses import dataclass

from . import player_table, utils
from .models import Goalie, Skater
from .season_stats import GOALIE, SKATER, read_season_stats


logger = logging.getLogger(__name__)
TOTALS = "tot"
AVERAGES = "avg"
DEFENCEMEN = "d"
FORWARDS = "f"
ALL_SKATERS = "t"
TEAM_IDENTITY_FIELDS = player_table.IDENTITY_FIELDS + ("pl_number",)


@dataclass
class TeamPlayer:
    player: object
    stats: dict
    is_favorite: bool

    def __getattr__(self, field):
        if field in self.stats:
            return self.stats[field]
        return getattr(self.player, field)

    def value(self, field):
        return getattr(self, field)


def project_team_players(team, user, season, player_type, euro):
    if season is None:
        return []
    model = Skater if player_type == SKATER else Goalie
    favorites = set()
    if user.is_authenticated:
        relation = user.favorite_skaters if player_type == SKATER else user.favorite_goalies
        favorites = set(relation.values_list("pk", flat=True))
    # Roster membership cannot identify historical participation. JSON containment
    # narrows candidates; the shared reader then selects the exact season split.
    candidates = model.objects.filter(sbs_stats__contains=[{"teamAbbr": team.abbr}]).only(
        *TEAM_IDENTITY_FIELDS, "sbs_stats"
    )
    result = []
    for player in candidates:
        try:
            source = read_season_stats(
                player.sbs_stats, season, player_type=player_type, team_abbr=team.abbr
            )
        except ValueError as error:
            logger.warning(
                "Skipping invalid team statistics for player %s, team %s: %s",
                player.nhl_id,
                team.abbr,
                error,
            )
            continue
        if source is None or source.totals["games"] is None or source.totals["games"] <= 0:
            continue
        stats = dict(source.totals)
        stats.update(source.averages or {})
        if euro:
            stats.update(height=player.height_cm, weight=player.weight_kg)
        result.append(TeamPlayer(player, stats, player.pk in favorites))
    return result


def empty_message(team, season, position=None):
    noun = {DEFENCEMEN: "defencemen", FORWARDS: "forwards", ALL_SKATERS: "skater"}.get(
        position, "goalie"
    )
    label = player_table.season_label(season) or "the selected season"
    return "No {} statistics are available for {} in {}.".format(noun, team.abbr, label)


def get_team_detail_context(team, user, season, stat_type=TOTALS):
    if stat_type not in (TOTALS, AVERAGES):
        raise ValueError("Invalid team statistics type")
    euro = utils.measurements_format_is_euro(user)
    skaters = project_team_players(team, user, season, SKATER, euro)
    goalies = project_team_players(team, user, season, GOALIE, euro)
    # Match the Players table's null-last ordering and stable tie handling.
    skaters = player_table.sort_rows(skaters, "col", [], euro, stat_type)
    goalies = player_table.sort_rows(goalies, "col", [], euro, "gls")
    groups = []
    for title, position, table_id, positions in (
        (utils.DEF, DEFENCEMEN, utils.TABLE_IDS[0], [utils.POSITIONS[1]]),
        (utils.FRW, FORWARDS, utils.TABLE_IDS[1], utils.POSITIONS[2:]),
    ):
        groups.append(
            {
                "type": title,
                "position_filter": position,
                "table_id": table_id,
                "list": [player for player in skaters if player.position_abbr in positions],
                "empty_message": empty_message(team, season, position),
            }
        )
    return {
        "team": team,
        "goalies": goalies,
        "skaters": groups,
        "all_skaters": skaters,
        "tbody_skaters": utils.TEMPLATES[6] if stat_type == TOTALS else utils.TEMPLATES[7],
        "tbody_goalies": "players/partial_goalies_team_detail.html",
        "table_mode": stat_type,
        "next_mode": AVERAGES if stat_type == TOTALS else TOTALS,
        "season_id": season or "",
        "season_label": player_table.season_label(season),
        "goalies_empty_message": empty_message(team, season),
    }


def skater_group(context, position):
    if position == ALL_SKATERS:
        return {"list": context["all_skaters"]}
    if position not in (DEFENCEMEN, FORWARDS):
        raise ValueError("Invalid team position filter")
    return next(group for group in context["skaters"] if group["position_filter"] == position)
