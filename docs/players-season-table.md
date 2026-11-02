# Season-specific Players table

The Players page and its ordinary `ajax_players` requests now use
`players.season_stats.read_season_stats` through `players.player_table`. Every
statistical column, including games played, comes from the selected SBS season.
Skater averages are calculated from totals; ordinary snapshot columns,
`stats_season_id`, and stored `sbs_stats_avg` do not decide the table's values or
membership. These reads do not modify player records.

## Selecting a season

The page defaults to the latest valid NHL regular season actually present in SBS
across skaters and goalies. The selector shows loaded seasons. A request such as
`/players/?season=20262027` explicitly selects a season; `2026-27` is also accepted.
A valid requested season stays selected even if nothing has been loaded for it.
There is no automatic switch to another season when a selection has no players.

Both AJAX tables keep the page's selected season through totals/averages switches,
goalie switches, filters and pagination. Direct AJAX callers can supply the same
`season` query parameter; omitting it selects the latest SBS season. No live NHL
requests or calendar-based season assumptions are needed to render a table.

Players without a matching season row, or without positive known games played,
are excluded. Missing individual statistics remain unavailable and display as
an em dash; zero remains zero. Invalid SBS structures are logged and excluded
rather than replaced with snapshot values. The page shows a clear empty message
when a season has no statistics or filters match no players. Empty ranges disable
sliders until values are available again.

## Teams, sorting and filters

The Team column and team filters use participation in the selected season,
rather than the player's current roster foreign key. A single-team season shows
that abbreviation; multiple known teams show `TOT` with the team names in its
tooltip. A team filter includes a traded player who played for that team, while
their row still displays overall season totals. The
[team detail tables](team-season-tables.md) show team-specific contributions.

Statistical filters and sorting operate on the same projected values as the
display, before pagination and rank numbering. Numeric filters support equality,
comparisons and inclusive ranges, including signed values and decimal averages.
TOI comparisons use `MM:SS`. Unknown statistics sort last in either direction,
and primary-key ordering resolves ties consistently. Metadata filters use player
attributes, including current age, measurements, nationality and the existing
rookie flag; historical versions of those attributes are not reconstructed.

Names retain their existing links and favorite stars. Team, nationality and
position checkbox options and slider ranges are derived from season-eligible
players, so players with only old statistics cannot contribute options to a newer
season's table. Metric-profile weight filters and display use kilograms.

## Query strategy and scope

The current JSON-array schema is projected and filtered in Python across the
candidate player set. Only page rows are serialized. Large unrelated JSON fields
and ordinary snapshot statistics are deferred. Favorite membership is fetched
once for an authenticated user, avoiding Django 2.2's per-row M2M serialization
queries. A regression check verifies that database query count does not grow with
the number of displayed players.

This strategy keeps season logic shared with the reader without a schema change.
CPU and memory work still grow with the candidate set and its stored season
history; dedicated season tables remain a possible later improvement if that
becomes a performance constraint.

Favorites/comparison now use the same reader; see [saved-list behavior and the
update workflow](saved-player-season-tables.md). Player-detail season selection
remains separate integration work. In particular, the authenticated favorites variation
of the shared AJAX endpoint keeps its existing data source in this commit.

Run the focused PostgreSQL tests using real migrations:

```bash
python -m pytest -c players/tests/pytest.ini players/tests/integration/tests_players_season_table.py
```

They cover stale and contradictory snapshots, sorting before pagination,
historical selection, traded players, nullable goalie rates, numeric filters,
metric profiles, empty seasons, favorite stars and query growth. As with the
loader persistence tests, use Django's isolated test database and do not pass
`--nomigrations` while the legacy ImageField schema issue remains.
