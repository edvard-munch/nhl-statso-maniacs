"""Complete selected-season filter populations, independent of catalogue pages."""

from .catalogue import (
    GOALIE,
    GOALIE_NUMBERS,
    SKATER_NUMBERS,
    catalogue_population,
    matches,
    value,
)

CATEGORICAL_FILTERS = frozenset({"team", "nation", "position"})


def ranges(rows, fields):
    result = {}
    for field in sorted(fields):
        known = [value(row, field) for row in rows if value(row, field) is not None]
        result[field] = {"min": min(known) if known else None, "max": max(known) if known else None}
    return result


def options(rows, code_field, label_field):
    # Stable identity ordering also makes conflicting legacy labels deterministic.
    labels = {}
    for row in sorted(rows, key=lambda row: row["nhl_id"]):
        code = row[code_field]
        if code:
            labels.setdefault(code, row[label_field] or code)
    return [{"code": code, "label": labels[code]} for code in sorted(labels)]


def catalogue_filters(query):
    initial, meta = catalogue_population(query)
    option_query = {key: item for key, item in query.items() if key not in CATEGORICAL_FILTERS}
    option_rows = [row for row in initial if matches(row, option_query)]
    filtered = [row for row in option_rows if matches(row, query)]
    teams = {team["abbr"]: team for row in option_rows for team in row["teams"]}
    fields = GOALIE_NUMBERS if meta["player_type"] == GOALIE else SKATER_NUMBERS
    return {
        "meta": meta,
        "initial_count": len(initial),
        "options_count": len(option_rows),
        "filtered_count": len(filtered),
        "options": {
            "teams": [teams[abbr] for abbr in sorted(teams)],
            "nations": options(option_rows, "nation_abbr", "nation"),
            "positions": options(option_rows, "position_abbr", "position_name"),
        },
        "initial_ranges": ranges(initial, fields),
        "filtered_ranges": ranges(filtered, fields),
        "height_values_cm": sorted(
            {row["height_cm"] for row in filtered if row["height_cm"] is not None}
        ),
    }
