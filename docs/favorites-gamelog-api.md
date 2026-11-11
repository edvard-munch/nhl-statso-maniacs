# Aggregated Favorites gamelog API

`GET /api/v1/me/favorites/gamelog/` combines saved game rows for the current
account's favorite skaters or goalies. Existing HTML/AJAX Favorites gamelogs remain
available. No loader calls, migrations or frontend changes are introduced.

## Ownership and response

A Django session is required; anonymous requests return 403
`authentication_required`. Responses are private/no-store and vary on Cookie.
GET/HEAD do not mutate domain data. Unsafe methods return 405. Favorites owned by
other accounts and players selected only for comparison are excluded.

The response contains `count`, `next`, `previous`, `results` and `meta`. Each result
has the [public gamelog entry shape](player-profile-api.md) plus `player`:

```json
{
  "player_type": "skater",
  "nhl_id": 8478402,
  "name": "Example Player",
  "last_name": "Player",
  "slug": "example-player",
  "position_abbr": "C"
}
```

This is current public identity metadata, not historical biography or a private
position override. Statistics, game position and sweater number come from the
verified saved game row. Durations are seconds and save percentages are fractions.
No raw JSON, snapshot fields, notes or other accounts' state are exposed.
Linked game summaries use the same [saved state evidence](game-state-api.md) as
public gamelogs, game detail and the scoreboard, including explicit conflict and
unknown observation time. Unlinked summaries remain null.

Metadata includes selected `player_type`, optional `season_id`, `ordering`,
`date_min`, `date_max` and the unfiltered combined Favorites `quota` described in
the [Favorites API contract](favorites-api.md). Counts represent filtered game
**rows**, not distinct games or players; two favorites in one game produce two
rows. Favorite players with no log or roster evidence produce no game rows, but
remain present in the ordinary Favorites list and quota.

## Queries and pagination

`player_type=skater` is the default; `goalie` selects the other typed group.
Omitting `season_id` returns **all stored seasons**, independently of the ordinary
Favorites list's selected SBS season or the calendar date. No legacy 200-row cap
is applied. An optional canonical season selects verified regular-season NHL game
IDs; dated orphan rows cannot establish season provenance and are excluded by
that filter.

Use the [public player gamelog query contract](player-profile-api.md) for:

- Inclusive `date_min` and `date_max` in strict `YYYY-MM-DD` format.
- Exact comma-separated `team` and `opponent` abbreviations from saved sides.
- Typed numeric `*_min`, `*_max`, `*_isnull` filters.
- Named `ordering` fields for date, game ID, teams and typed game statistics;
  goalie `decision` is also supported. Favorites additionally allow `player_name`,
  `player_last_name` and `player_nhl_id`, as described below. Default: `-date`.
- `page` and `page_size` (default 50, maximum 100).

`search` additionally matches a literal, case-insensitive favorite player name
substring. Percent signs, underscores and quotes have no special search meaning.
Unknown/duplicate parameters, invalid dates/ranges, wrong-type statistics and
`mode` selectors are rejected with 400. There is no `mode` parameter here.

All filters and global sorting precede pagination. Unknown dates/statistics sort
last in either direction. Date, game ID, case-folded last name and NHL ID provide
stable ties within a typed group. Empty first pages return 200; later out-of-range
pages return 404. A membership change between requests can change pages; this is
not a cursor or revision protocol.

## Verification and execution

The batch reader shares the public player gamelog/game-detail verification rules:

- A saved game must include the player in a typed roster before its statistics
  can be verified. A game stamp in an orphan date row is insufficient.
- Stamped game/player identity must match. Legacy unstamped rows also require
  saved team/opponent evidence and no same-player date collision.
- Multiple favorite players in the same game/date are independent. A collision
  for one player does not invalidate another player's row.
- Duplicate roster groups, wrong identity/type and ambiguous evidence remain
  `unverified`. Orphans and malformed/missing rows retain explicit availability
  with null statistic fields; valid zero values are preserved.
- Undated linked games remain visible with missing statistics and a null date;
  date bounds exclude them. Invalid JSON date keys are skipped.

The account's existing owner-row lock is held through membership loading,
projection, quota reads and serialization, shared with Favorites mutation APIs
and legacy writers. A read waits for a competing membership change and then uses
the updated selection. Unrelated accounts do not share that lock. Game loaders
use their separate locks; this is not a database-wide game-data snapshot.

Roster evidence is loaded in a bounded number of queries per player type rather
than one query per favorite or game. Query counts stay bounded as the history
grows, but processing and response preparation still scale with saved history.
No SBS, career or current-statistics fallback is used.


## Player identity ordering

The aggregated Favorites resource additionally accepts:

- `player_name`: current public `player.name`, using Unicode casefold.
- `player_last_name`: current public `player.last_name`, using Unicode casefold.
- `player_nhl_id`: numeric public NHL ID, never the database primary key.

Prefix a field with `-` for descending order. Empty or whitespace-only names are
unknown and sort last in either direction; their original response values are
preserved. Names use casefold ordering, not locale-specific collation. For example,
`?ordering=player_name,-date&page_size=25` groups favorite players by name and
shows their newest dated rows first. Filtering and all ordering run globally
before pagination; following page links preserves the complete requested order.

Multiple distinct allowlisted keys are applied left to right. Existing final ties
remain ascending date, saved game NHL ID, casefold last name and typed player
identity (`player_type`, numeric NHL ID). The existing implicit tie placeholders
put missing date/game evidence before known values; explicit sort fields still
put unknown values last in either direction. Request `-date` explicitly after a
name key when newest-first rows within each name are desired. The default `-date`
behavior is unchanged.

`player_type` still selects one favorite group per request. A goalie and skater
sharing the same NHL ID never become one identity or enter the other group.
Unlinked/unverified rows retain their public identity, even when game/statistic
evidence is unknown, so identity sorting does not invent missing statistics or
silently discard those rows. Existing type-specific statistic filters and ordering
can be combined with identity keys; the combined quota remains unfiltered.

These keys are exclusive to this aggregated endpoint. Individual public player
gamelogs reject them. Nested ORM/JSON paths, duplicate or contradictory directions
for the same key, unsupported fields and wrong-player-type statistics return 400.
Identity ordering does not add identity-range filters or a mixed-player-type mode.
Owner selection, session requirements, locks and private response behavior remain
unchanged; sorting adds no database queries and does not load SBS/career snapshots.
