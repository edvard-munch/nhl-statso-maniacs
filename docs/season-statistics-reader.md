# Shared season statistics reader

`players.season_stats.read_season_stats` reads the stored `sbs_stats` array and
returns table field names, with no ORM access, network requests, or mutations.
Page integration and loader changes are separate commits.

```python
from players.season_stats import SKATER, read_season_stats

stats = read_season_stats(player.sbs_stats, "20262027", player_type=SKATER)
if stats is not None:
    goals = stats.totals["goals"]
    goals_per_game = stats.averages["goals_avg"]

team_stats = read_season_stats(
    player.sbs_stats, "2026-27", player_type=SKATER, team_abbr="BUF"
)
```

Use `player_type=GOALIE` for goalies. The result is a `SeasonStatistics` object
with a canonical eight-digit `season_id`, the requested `team_abbr` (or `None`
for overall statistics), and fresh `totals` and `averages` dictionaries. Goalies
have `averages=None`, since their table has no skater-style per-game mode.

The caller chooses the season explicitly. Season IDs may be integers or strings;
stored labels such as `2026-27` are also supported. A missing season or team
returns `None`. A present row with missing fields returns a result whose affected
values are `None`; genuine zeros remain zero. Zero or unknown games make counting
averages unavailable. Snapshot columns and `sbs_stats_avg` are never consulted.

## Combining team splits

Without a team filter, counting statistics are summed across distinct team rows,
and skater per-game averages use combined counts divided by combined games,
rounded to two decimals. A missing count in any split makes that combined count
and its average unavailable. TOI values are weighted by games and rounded to the
nearest second; zero-game splits do not affect TOI. Missing or malformed time in
a played split makes that time statistic unavailable. Input times use `MM:SS`,
where the minutes component can exceed 59. Source per-game times may already be
rounded, so combined times are approximations.

An explicit combined row identified by `teamAbbr=TOT` or a numeric multi-team
marker such as `2TM` takes precedence over splits for overall statistics, avoiding
double counting. The reader does not guess combined rows from team names or
missing abbreviations. A team filter uses that team's row even when a combined
row is present. Multiple combined rows or duplicate team rows raise `ValueError`
rather than silently adding potentially duplicated values. Multiple splits must
have distinct `teamAbbr` values.

For goalies, missing saves are derived from `shotsAgainst - goalsAgainst` when
both inputs exist. A single row preserves supplied GAA and save percentage.
Across team splits, save percentage is computed from combined saves divided by
combined shots, rounded to three decimals. GAA remains `None`: correctly combining
it requires actual goalie ice time, which this contract does not currently
provide. A combined-season row can supply GAA directly. Rates are never averaged
by games played.

## Data boundaries and limitations

Explicit non-NHL or non-regular-season rows are excluded. Stored SBS rows without
league/game-type metadata are accepted because the loader already selects NHL
regular seasons. Rows with invalid or missing season labels cannot match a
requested season. Invalid requested seasons, player types, team filters, nonempty
non-list data, and non-dictionary rows raise `ValueError`. Null/empty stored data
(including the legacy empty dictionary) returns `None`. Numeric strings and
non-finite or boolean statistics are treated as unavailable, not coerced.

The reader cannot repair previously contaminated enrichment values or identify
which fields were copied from an old snapshot. The loaders now replace refreshed
seasons with report-derived rows; untouched historical rows may still need a full
refresh. See [loader behavior](season-statistics-loaders.md). The pure reader does
not access the database. The [Players table integration](players-season-table.md)
now projects its results for filtering, sorting and pagination.
The [team table integration](team-season-tables.md) uses the same reader with an
explicit team abbreviation for initial rendering and AJAX switches.

Run the reader tests using the existing Python 3.7 virtual environment:

```bash
python -m pytest -c players/tests/pytest.ini players/tests/unit/other/tests_season_stats_reader.py
```
