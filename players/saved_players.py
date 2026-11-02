"""Season-aware saved-player displays; selections themselves remain untouched."""

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.template.loader import render_to_string

from . import player_table, utils


SKATERS = "skaters"
GOALIES = "goalies"
SEASON_TOTALS = "season_tot"
SEASON_AVERAGES = "season_avg"
CAREER_TOTALS = "career_tot"
CAREER_AVERAGES = "career_avg"
ALLOWED_MODES = {
    SKATERS: (SEASON_TOTALS, SEASON_AVERAGES, CAREER_TOTALS, CAREER_AVERAGES),
    GOALIES: (SEASON_TOTALS, CAREER_TOTALS),
}
SKATER_METRICS = (
    ("Games", "games", "gamesPlayed", None),
    ("Goals", "goals", "goals", None),
    ("Assists", "assists", "assists", None),
    ("Points", "points", "points", None),
    ("+/-", "plus_minus", "plusMinus", None),
    ("PIM", "penalty_min", "pim", None),
    ("SOG", "shots", "shots", None),
    ("Hits", "hits", "hits", None),
    ("Bks", "blocks", "blocked", None),
    ("FW", "faceoff_wins", "faceoffsWon", None),
    ("PPP", "pp_points", "powerPlayPoints", None),
    ("SHP", "sh_points", "shorthandedPoints", None),
    ("TOI", "time_on_ice", "avgToi", None),
    ("TOI PP", "time_on_ice_pp", "powerPlayTimeOnIcePerGame", None),
    ("TOI SH", "time_on_ice_sh", "shortHandedTimeOnIcePerGame", None),
)
GOALIE_METRICS = (
    ("Games", "games", "gamesPlayed", None),
    ("W", "wins", "wins", None),
    ("L", "losses", "losses", None),
    ("OTL", "ot_losses", "otLosses", None),
    ("GAA", "goals_against_av", "goalsAgainstAvg", 2),
    ("SV %", "saves_perc", "savePctg", 3),
    ("SV", "saves", "saves", None),
    ("SHO", "shotouts", "shutouts", None),
)
CAREER_ALIASES = {
    "gamesPlayed": ("games",),
    "shorthandedPoints": ("shortHandedPoints",),
    "avgToi": ("timeOnIcePerGame",),
    "otLosses": ("ot",),
    "goalsAgainstAvg": ("goalAgainstAverage", "goalsAgainstAverage"),
    "savePctg": ("savePercentage", "savePct"),
}
AVERAGE_PRECISION = 2


@dataclass
class SavedPlayer:
    player: object
    fields: dict
    is_favorite: bool
    season_available: bool
    season_status: str

    def __getattr__(self, field):
        if field in self.fields:
            return self.fields[field]
        return getattr(self.player, field)


def validate_modes(skater_mode, goalie_mode):
    if skater_mode not in ALLOWED_MODES[SKATERS] or goalie_mode not in ALLOWED_MODES[GOALIES]:
        raise ValueError("Invalid comparison statistics mode")


def selection(request):
    season = player_table.selected_season(request.GET.get("season"))
    skater_mode = request.GET.get("skater_mode", SEASON_TOTALS)
    goalie_mode = request.GET.get("goalie_mode", SEASON_TOTALS)
    validate_modes(skater_mode, goalie_mode)
    return season, skater_mode, goalie_mode


def _career(source):
    result = deepcopy(source) if isinstance(source, dict) else {}
    for key, aliases in CAREER_ALIASES.items():
        if result.get(key) is None:
            result[key] = next(
                (result[alias] for alias in aliases if result.get(alias) is not None), None
            )
    return result


def _players(user, season, player_type, euro):
    extras = (
        ("image", "career_stats", "career_stats_avg")
        if player_type == SKATERS
        else ("image", "career_stats")
    )
    rows = player_table.project_players(
        season,
        "tot" if player_type == SKATERS else "gls",
        user,
        player_table.COMPARISON,
        extras,
    )
    result = []
    for row in sorted(rows, key=lambda item: item.player.pk):
        fields = dict(row.stats)
        abbr, name = fields["team"]
        fields["team"] = SimpleNamespace(abbr=abbr, name=name)
        fields["career_stats"] = _career(row.player.career_stats)
        fields["career_stats_avg"] = (
            _career(row.player.career_stats_avg) if player_type == SKATERS else {}
        )
        if euro:
            fields.update(height=row.player.height_cm, weight=row.player.weight_kg)
        status = (
            player_table.season_label(season)
            if row.season_available
            else player_table.unavailable_message(season)
        )
        if row.season_available and row.stats["games"] == 0:
            status = "No games played in {}".format(player_table.season_label(season))
        result.append(SavedPlayer(row.player, fields, row.favorited, row.season_available, status))
    return result


def statistic_rows(players, player_type, mode):
    career = mode in (CAREER_TOTALS, CAREER_AVERAGES)
    average = mode in (SEASON_AVERAGES, CAREER_AVERAGES)
    metrics = SKATER_METRICS if player_type == SKATERS else GOALIE_METRICS
    result = [
        {
            "label": "Statistics",
            "values": [
                "Career statistics" if career else player.season_status for player in players
            ],
        }
    ]
    for label, field, career_key, precision in metrics:
        values = []
        for player in players:
            if career:
                source = player.career_stats_avg if average else player.career_stats
                value = source.get(career_key)
            else:
                key = field + "_avg" if average and field in utils.COLUMNS_TOT else field
                value = player.fields[key]
            digits = (
                precision
                if precision is not None
                else (AVERAGE_PRECISION if average and field in utils.COLUMNS_TOT else None)
            )
            if digits is not None and value is not None:
                try:
                    number = Decimal(str(value))
                    value = format(number, ".{}f".format(digits)) if number.is_finite() else None
                except (InvalidOperation, ValueError):
                    value = None
            values.append(value)
        result.append({"label": label, "values": values})
    return result


def comparison_context(user, season, skater_mode=SEASON_TOTALS, goalie_mode=SEASON_TOTALS):
    validate_modes(skater_mode, goalie_mode)
    euro = utils.measurements_format_is_euro(user)
    skaters = _players(user, season, SKATERS, euro)
    goalies = _players(user, season, GOALIES, euro)
    return {
        "comp_skt": skaters,
        "comp_gls": goalies,
        "numb_of_skaters": len(skaters),
        "numb_of_goalies": len(goalies),
        "empty": not skaters and not goalies,
        "skater_rows": statistic_rows(skaters, SKATERS, skater_mode),
        "goalie_rows": statistic_rows(goalies, GOALIES, goalie_mode),
        "skater_mode": skater_mode,
        "goalie_mode": goalie_mode,
        "season_id": season or "",
        "season_label": player_table.season_label(season),
    }


def comparison_payload(context, request):
    return {
        "compare_skaters": render_to_string(
            "players/partial_skaters_comparison_base.html", context, request=request
        ),
        "compare_goalies": render_to_string(
            "players/partial_goalies_comparison_base.html", context, request=request
        ),
        "skaters_button": "SKATERS ({})".format(context["numb_of_skaters"]),
        "goalies_button": "GOALIES ({})".format(context["numb_of_goalies"]),
        "skaters_count": context["numb_of_skaters"],
        "goalies_count": context["numb_of_goalies"],
        "skater_mode": context["skater_mode"],
        "goalie_mode": context["goalie_mode"],
        "season_id": context["season_id"],
    }
