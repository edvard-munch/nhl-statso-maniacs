# Maintaining season statistics

`players.season_loading` assembles statistics directly from NHL stats/rest reports.
The regular-season summary is the base row; skaters also use realtime, faceoffwins
and timeonice. All statistical keys expected by the shared reader are present.
Missing optional report rows or values produce nulls, including a genuine
distinction between unknown and zero. Per-game averages are derived from the
fresh totals, including hits, blocks and faceoffs. Saved `sbs_stats_avg` uses SBS
key names, while ordinary snapshot columns use the existing model field names.

## Commands

- `upd_pls` fetches bios and all season reports in bulk. It stages all player rows,
  including any traded-player team queries, before starting a database transaction.
  The transaction updates metadata, ordinary columns, season marker, SBS totals,
  averages and multi-team metadata together. A database error rolls back the whole
  publication. Flag-file handling runs afterward.
- `upd_pls_tot --mode=current` detects the season once and fetches season reports
  in bulk, then refreshes each existing player's season rows and career enrichment.
  It can create a missing season row and does not call the landing endpoint. Each
  player's prepared fields are written in one save; if a later player fails,
  earlier coherent player updates remain committed.
- `upd_pls_tot --mode=full` still obtains profile/career information from landing
  responses. It obtains NHL season statistics from the same report assembly path,
  across all returned seasons, rather than copying ordinary snapshot columns into
  landing rows. Publication remains per player.

Fresh rows replace the entire corresponding season in SBS and its averages.
Other seasons are preserved, including extra metadata and historical averages.
Repeated runs replace existing season rows rather than appending duplicates.
If the summary has no row for a player, their existing season data and marker
are preserved; no season is invented from old snapshot columns. Refreshing an
older season does not downgrade a newer snapshot marker or ordinary statistics.

## Traded players

Reports identify a player's participating teams through `teamAbbrevs`. A
single-team season gets that team's abbreviation. For multi-team seasons, the
combined report becomes a `TOT` row and each team's contributions are requested
separately using `teamId` in `cayenneExp`, alongside player and season filters.
Whole-season totals are never copied into individual team rows. This also
preserves supplied overall goalie rates without guessing GAA from game counts.
The existing career tables will display the new `TOT` row as well as team splits.

Team IDs come from stored team metadata. Historical teams missing from the local
database are resolved through the NHL team registry, without creating or changing
team records. Unknown teams, duplicate summary rows, unscoped split responses,
disagreements about games/teams, and inconsistent combined/split summary counts
stop the update before publishing that data. Multi-team counts exclude `TOT`.

## Request failures and existing data

Report requests have a timeout, a bounded retry count, status/JSON checks and
pagination. Failed or malformed reports raise a command error instead of looking
like successful empty results. Optional reports that successfully return no rows
leave their statistical fields unavailable; they do not inherit values from a
previous run or season.

The model's ordinary TOI columns and goalie shutout column are not nullable.
Their cache uses empty strings and zero, respectively, where necessary; SBS
preserves nulls. The upcoming page integration should use the reader's values.
An update cannot retroactively repair untouched historical rows. Run full mode
to refresh the historical seasons returned by the NHL reports.

The legacy season parser/enrichment helpers remain available for their existing
callers and tests; these commands no longer use snapshot-to-SBS copying or
season-only enrichment. No model or migration changes are part of this step.
Existing pages still use their current data sources until their integration
commits.

## Regression checks

Synthetic stats/rest inputs are in `players/tests/fixtures/season_reports.json`,
paired with the existing expected table values in `season_stats.json`. Unit tests
cover report mapping, pagination, failures, repeatability and history preservation:

```bash
python -m pytest -c players/tests/pytest.ini players/tests/unit/other/tests_season_loading.py
```

Persistence tests use Django's normal isolated PostgreSQL test database and real
migrations. They cover new seasons, new goalies, team contributions, repeat runs,
favorites/comparison preservation, failed requests and transaction rollback:

```bash
python -m pytest -c players/tests/pytest.ini players/tests/integration/tests_season_loading_db.py
```

These checks mock report responses and media-file decisions. They do not load
live NHL data into the application database. Do not use `--nomigrations` for this
suite: the legacy model's `ImageField(max_length=None)` prevents schema creation
directly from models on this Django version; the real migrations create valid
columns. Other known full-suite collection/isolation issues are separate work.
