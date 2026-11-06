# Season-specific team tables

Team detail pages and `ajax_stats_switcher` now read the requested team's season
contributions through the shared season reader. `players.team_tables` provides
the same projection for initial goalies/defencemen/forwards tables and AJAX
totals, averages, joined skaters and split groups.

## Season and participation

The season selector uses the same rules as the Players page: default to the latest
valid NHL regular season present in SBS across all players, or accept an explicit
`season` query parameter such as `20262027` or `2026-27`. A team with only older
data does not choose an older default. Valid unloaded seasons remain selected and
show empty tables. Invalid seasons, modes and position filters return HTTP 400;
missing teams or incorrect slugs remain HTTP 404.

Table membership comes from SBS rows with the selected season and exact team
abbreviation. Positive known games played are required. The current roster foreign
key, snapshot season marker and ordinary statistics columns are not used to infer
participation or missing statistics. A former player can therefore appear for a
team they represented in that season, while a current roster member with only old
statistics is excluded. Combined `TOT` rows cannot substitute for missing team
splits.

Unlike the Players table's overall totals, these tables show the team's own
contribution. For example, a traded player's 4 COL games / 1 goal and 6 BUF games /
3 goals display separately on the two team pages. BUF averages use 6 games as
their denominator, not the combined 10. Goalie rates come from the exact team row.
Unknown statistics display as an em dash; zero values remain visible.

Identity, position classification, jersey number and measurements still use the
player's current profile metadata. Metric measurements are applied to read-only
display objects. Favorite stars use the current user's saved memberships, including
former players; rendering never changes those memberships or player records.

## AJAX controls and ordering

Totals/averages and joined/split controls carry the page's selected season.
Joining retains the defencemen section's current mode. Splitting restores both
groups in the joined table's current mode. Controls prevent overlapping requests;
both split responses must succeed before replacing a joined table. Request
failures leave the previous table visible with a retry message.

Server ordering follows the shared Players table ordering: totals by points,
averages by points per game, and goalies by wins, with unknown values last and
stable primary-key tie handling. Client-side table sorting and rank numbering
continue to operate on the rendered team-specific values.

## Database strategy and tests

PostgreSQL JSON containment narrows candidates to players with an SBS row for
the team. The reader then checks the exact season and split. Unrelated JSON fields
and snapshot statistics are deferred; favorite membership is fetched in bulk.
Regression tests verify that query count does not grow with rendered player count.
No model, migration or data backfill is part of this change. Existing missing or
contaminated team splits require a report-based loader refresh.

Run the focused suite against Django's isolated PostgreSQL test database using
real migrations:

```bash
uv run --locked python -m pytest -c players/tests/pytest.ini players/tests/integration/tests_team_season_tables.py
```

It covers initial/AJAX parity, traded skaters and goalies, historical and empty
seasons, stale roster links, combined-only rows, nullable rates, metric profiles,
favorite stars, read-only behavior and query growth. It also checks the rendered
table cells and goalie row structure. JavaScript syntax is checked with
`node --check players/static/players/ajax_switch_stats.js`.

Favorites/comparison now use the shared reader; see [saved-list behavior and the
update workflow](saved-player-season-tables.md). Player-detail season selection
remains separate integration work.
