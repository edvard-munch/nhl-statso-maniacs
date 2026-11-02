"""Season-specific projection, filtering and pagination for the Players table."""

import json
import logging
import operator
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import chain
from urllib.parse import parse_qsl

from django.core import serializers
from django.utils.html import format_html

from . import utils
from .models import Goalie, Skater, Team
from .season_stats import (
    COMBINED_TEAM_PATTERN,
    GOALIE,
    NHL_LEAGUE,
    REGULAR_SEASON,
    SKATER,
    normalize_season_id,
    read_season_stats,
)


logger = logging.getLogger(__name__)
IDENTITY_FIELDS = (
    "slug",
    "nhl_id",
    "name",
    "last_name",
    "position_abbr",
    "position_name",
    "nation_abbr",
    "nation",
    "height",
    "height_cm",
    "weight",
    "weight_kg",
    "birth_date",
    "age",
    "draft_number",
    "draft_year",
    "rookie",
)
TABLE_COLUMNS = {
    "tot": utils.COLUMNS + utils.COLUMNS_TOT + utils.COLUMNS_TOI,
    "avg": utils.COLUMNS + utils.COLUMNS_AVG + utils.COLUMNS_TOI,
    "gls": utils.COLUMNS + utils.COLUMNS_GOALIES,
}
FILTER_KEY_PATTERN = re.compile(r"^fcol\[(\d+)\]$")
SORT_KEY_PATTERN = re.compile(r"^col\[(\d+)\]$")
NUMBER_PATTERN = r"-?\d+(?:\.\d+)?"
RANGE_PATTERN = re.compile(r"^({0})\s*(?:-|to)\s*({0})$".format(NUMBER_PATTERN))
COMPARISON_PATTERN = re.compile(r"^(<=|>=|!=|=|<|>)?\s*(.+)$")
TIME_PATTERN = re.compile(r"^(\d+):([0-5]\d)$")
COMPARISONS = {
    "=": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}
TIME_FIELDS = {"time_on_ice", "time_on_ice_pp", "time_on_ice_sh"}
NUMERIC_FIELDS = set(
    chain(
        utils.COLUMNS_TOT,
        utils.COLUMNS_AVG,
        utils.COLUMNS_GOALIES,
        ("games", "height_cm", "weight", "weight_kg", "age", "draft_number", "draft_year"),
    )
)
SECONDS_PER_MINUTE = 60
MISSING_VALUE = "—"
FAVORITES = "favorites"
COMPARISON = "comparison"


def season_label(season_id):
    return "{}-{}".format(season_id[:4], season_id[-2:]) if season_id else None


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


def selected_season(value, seasons=None):
    if value is not None:
        return normalize_season_id(value)
    seasons = available_seasons() if seasons is None else seasons
    return seasons[0] if seasons else None


def season_context(value):
    seasons = available_seasons()
    season = selected_season(value, seasons)
    if season and season not in seasons:
        seasons = sorted(seasons + [season], reverse=True)
    return {
        "season_id": season or "",
        "season_label": season_label(season),
        "season_options": [(item, season_label(item)) for item in seasons],
    }


@dataclass
class PlayerRow:
    player: object
    stats: dict
    favorited: bool
    teams: tuple
    season_available: bool = True

    def value(self, field):
        if field in self.stats:
            return self.stats[field]
        if field == "favoriting":
            return self.favorited
        if field == "number":
            return self.player.pk
        value = self.player
        for part in field.split("__"):
            value = getattr(value, part, None)
            if value is None:
                break
        return value


def empty_statistics(player_type):
    fields = (
        {"games", *utils.COLUMNS_GOALIES}
        if player_type == GOALIE
        else {"games", *utils.COLUMNS_TOT, *utils.COLUMNS_AVG, *utils.COLUMNS_TOI}
    )
    return dict.fromkeys(fields)


def unavailable_message(season):
    return (
        "No statistics for {}".format(season_label(season))
        if season
        else "No season statistics loaded"
    )


def project_players(season, stat_type, user, collection=None, extra_fields=()):
    if collection not in (None, FAVORITES, COMPARISON):
        raise ValueError("Invalid saved-player collection")
    if (season is None and collection is None) or (collection and not user.is_authenticated):
        return []
    model = Goalie if stat_type == "gls" else Skater
    player_type = GOALIE if stat_type == "gls" else SKATER
    favorites = set()
    if user.is_authenticated and collection != FAVORITES:
        relation = user.favorite_goalies if player_type == GOALIE else user.favorite_skaters
        favorites = set(relation.values_list("pk", flat=True))
    if collection:
        relation_name = "favorite_" if collection == FAVORITES else "comparable_"
        queryset = getattr(
            user, relation_name + ("goalies" if player_type == GOALIE else "skaters")
        )
    else:
        queryset = model.objects
    queryset = queryset.only(*IDENTITY_FIELDS, "sbs_stats", *extra_fields)
    team_names = dict(Team.objects.values_list("abbr", "name"))
    result = []
    for player in queryset:
        try:
            stats = (
                read_season_stats(player.sbs_stats, season, player_type=player_type)
                if season
                else None
            )
        except ValueError as error:
            logger.warning(
                "Skipping invalid season statistics for player %s: %s", player.nhl_id, error
            )
            stats = None
        if collection is None and (
            stats is None or stats.totals["games"] is None or stats.totals["games"] <= 0
        ):
            continue
        fields = empty_statistics(player_type)
        if stats is not None:
            fields.update(stats.totals)
            fields.update(stats.averages or {})
        teams = set()
        for row in player.sbs_stats if stats is not None else []:
            try:
                if normalize_season_id(row.get("season")) != season:
                    continue
            except ValueError:
                continue
            if (
                row.get("leagueAbbrev", NHL_LEAGUE) != NHL_LEAGUE
                or row.get("gameTypeId", REGULAR_SEASON) != REGULAR_SEASON
            ):
                continue
            abbr = row.get("teamAbbr")
            if isinstance(abbr, str) and abbr and not COMBINED_TEAM_PATTERN.fullmatch(abbr):
                teams.add((abbr, team_names.get(abbr, abbr)))
        teams = tuple(sorted(teams))
        if len(teams) == 1:
            team_display = teams[0]
        elif teams:
            team_display = ("TOT", ", ".join(name for abbr, name in teams))
        else:
            team_display = (MISSING_VALUE, "Season team unavailable")
        fields.update(
            {"team": team_display, "team__abbr": team_display[0], "team__name": team_display[1]}
        )
        result.append(
            PlayerRow(
                player,
                fields,
                collection == FAVORITES or player.pk in favorites,
                teams,
                stats is not None,
            )
        )
    return result


def _column_field(column, columns, euro, sorting=False):
    if column < 0 or column >= len(columns):
        raise ValueError("Invalid table column")
    field = columns[column]
    if field == "name" and sorting:
        return "last_name"
    if field == "team":
        return "team__abbr"
    if field == "nation_abbr" and not sorting:
        return "nation"
    if field == "height":
        return "height_cm"
    if field == "weight" and euro:
        return "weight_kg"
    return field


def _numeric(value, field):
    if value is None:
        return None
    if field in TIME_FIELDS:
        match = TIME_PATTERN.fullmatch(str(value))
        if not match:
            return None
        minutes, seconds = map(int, match.groups())
        return Decimal(minutes * SECONDS_PER_MINUTE + seconds)
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def _matches(row, field, expression):
    value = row.value(field)
    if expression == MISSING_VALUE:
        return value is None
    if field in NUMERIC_FIELDS or field in TIME_FIELDS:
        value = _numeric(value, field)
        if value is None:
            return False
        bounds = RANGE_PATTERN.fullmatch(expression)
        if bounds:
            low, high = (_numeric(bound, field) for bound in bounds.groups())
            return low is not None and high is not None and low <= value <= high
        match = COMPARISON_PATTERN.fullmatch(expression)
        if match is None:
            return False
        comparison, operand = match.groups()
        operand = _numeric(operand, field)
        return operand is not None and COMPARISONS[comparison or "="](value, operand)
    if field == "team__abbr":
        return (
            any(expression.casefold() in abbr.casefold() for abbr, name in row.teams)
            or expression.casefold() in str(value).casefold()
        )
    return value is not None and expression.casefold() in str(value).casefold()


def filter_rows(rows, filt_col, columns, euro):
    for key, expression in parse_qsl(filt_col):
        match = FILTER_KEY_PATTERN.fullmatch(key)
        if match and expression.strip():
            field = _column_field(int(match.group(1)), columns, euro)
            rows = [row for row in rows if _matches(row, field, expression.strip())]
    return rows


def sort_rows(rows, sort_col, columns, euro, stat_type):
    ordering = []
    for key, direction in parse_qsl(sort_col):
        match = SORT_KEY_PATTERN.fullmatch(key)
        if match:
            if direction not in ("0", "1"):
                raise ValueError("Invalid sort direction")
            ordering.append(
                (_column_field(int(match.group(1)), columns, euro, True), direction == "1")
            )
    if not ordering:
        ordering = [
            (field.lstrip("-"), field.startswith("-")) for field in utils.DEFAULT_SORTING[stat_type]
        ]
    result = sorted(rows, key=lambda row: row.player.pk)
    for field, descending in reversed(ordering):
        known = [row for row in result if row.value(field) is not None]
        unknown = [row for row in result if row.value(field) is None]

        def key(row):
            value = row.value(field)
            if field in TIME_FIELDS:
                return _numeric(value, field)
            return value.casefold() if isinstance(value, str) else value

        result = sorted(known, key=key, reverse=descending) + unknown
    return result


def _range(rows, field):
    values = [row.value(field) for row in rows if row.value(field) is not None]
    return (min(values), max(values)) if values else (None, None)


def _options(rows, *fields):
    values = {
        tuple(row.value(field) for field in fields) + ((None,) if len(fields) == 1 else ())
        for row in rows
    }
    return sorted(values, key=lambda item: (item[0] is None, item[0]))


def _checkboxes(value):
    raw = value.partition("=")[2]
    filters = json.loads(raw) if raw else {}
    if not isinstance(filters, dict):
        raise ValueError("Invalid checkbox filters")
    for key in ("teams", "positions", "nations"):
        if key in filters and (
            not isinstance(filters[key], list)
            or any(not isinstance(item, str) for item in filters[key])
        ):
            raise ValueError("Invalid checkbox filters")
    return filters


def build_table(
    request,
    season,
    stat_type,
    page,
    size,
    sort_col,
    filt_col,
    rookie_filt,
    checkbox_filt,
    collection=None,
):
    if stat_type not in TABLE_COLUMNS:
        raise ValueError("Invalid statistics type")
    page = int(page.partition("=")[2])
    if page < 1:
        raise ValueError("Invalid page")
    columns = TABLE_COLUMNS[stat_type]
    euro = utils.measurements_format_is_euro(request.user)
    weight = "weight_kg" if euro else "weight"
    initial = project_players(season, stat_type, request.user, collection)
    rows = filter_rows(initial, filt_col, columns, euro)
    if rookie_filt.partition("=")[2].lower() == "true":
        rows = [row for row in rows if row.player.rookie]
    team_options = sorted({team for row in rows for team in row.teams})
    nation_options = _options(rows, "nation")
    position_options = _options(rows, "position_abbr", "position_name")
    filters = _checkboxes(checkbox_filt)
    for key, field in (
        ("teams", "team__abbr"),
        ("positions", "position_abbr"),
        ("nations", "nation"),
    ):
        if filters.get(key):
            if key == "teams":
                rows = [
                    row for row in rows if any(abbr in filters[key] for abbr, name in row.teams)
                ]
            else:
                rows = [row for row in rows if row.value(field) in filters[key]]
    total = len(rows)
    raw_size = size.partition("=")[2]
    size = total if raw_size.lower() == "all" else int(raw_size)
    if size < 0 or (size == 0 and raw_size.lower() != "all"):
        raise ValueError("Invalid page size")
    start = size * (page - 1)
    selected = sort_rows(rows, sort_col, columns, euro, stat_type)[start : start + size]
    players = [row.player for row in selected]
    serialized = json.loads(
        serializers.serialize(
            "json", players, use_natural_foreign_keys=True, fields=IDENTITY_FIELDS
        )
    )
    for source, row in zip(serialized, selected):
        source["fields"].update(row.stats)
        # Django 2.2's M2M serializer bypasses prefetch caches. The star needs
        # only this user's membership, which was fetched once during projection.
        source["fields"]["favoriting"] = [[request.user.username]] if row.favorited else []
    data = utils.process_json(request, columns, request.get_host(), serialized, total, start)
    if collection == FAVORITES:
        for cells, row in zip(data["rows"], selected):
            if not row.season_available:
                cells[columns.index("name")] += format_html(
                    '<br><small class="season-unavailable">{}</small>', unavailable_message(season)
                )
        data["season_availability"] = [row.season_available for row in selected]
    data.update(
        {
            "season_id": season,
            "season_label": season_label(season),
            "initial_age_range": _range(initial, "age"),
            "initial_weight_range": _range(initial, weight),
            "initial_height_range": _range(initial, "height_cm"),
            "age_range": _range(rows, "age"),
            "weight_range": _range(rows, weight),
            "height_range": _range(rows, "height_cm"),
            "fav_alert_div": utils.get_fav_alert_div(),
            "empty_message": (
                "No player statistics have been loaded."
                if season is None
                else "No player statistics are available for {}.".format(season_label(season))
            )
            if not initial
            else "No players match these filters.",
        }
    )
    for key, options, tip, css in (
        ("teams", team_options, True, "team"),
        ("nations", nation_options, False, "nation"),
        ("positions", position_options, True, "position"),
    ):
        data["all_" + key] = utils.checkbox(
            options, css + "_checkboxradio_skt", tip=tip, checked=filters.get(key), check_this=False
        )
    heights = sorted({row.value("height_cm") for row in rows if row.value("height_cm") is not None})
    data["height_values"] = (
        heights
        if euro
        else {
            row.value("height_cm"): row.value("height")
            for row in rows
            if row.value("height_cm") is not None
        }
    )
    return data
