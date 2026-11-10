# Teams JSON API

Three public read-only routes expose saved team metadata and selected-season
player contributions. They reuse the [Players API contract](players-api.md),
shared SBS reader and [existing team-table rules](team-season-tables.md).
Requests never run loaders, call NHL services, write records or load private state.
Existing HTML pages and AJAX contracts remain unchanged.

## Saved teams list

`GET /api/v1/teams/` returns all saved identities, including historical teams and
teams without loaded player statistics. It does not infer active status or
season participation from current metadata. `season_id` is not accepted here.

The response is `count`, `next`, `previous`, `results`, `meta`. Each team contains:
`nhl_id`, `name`, `abbr`, `slug`, `image_url` (null for no saved image),
`arena_name`, `arena_location`, `division`, `conference`, `website_url` and
`nhl_debut`. Empty saved strings remain strings. Image URLs are resolved without
checking file existence; external websites are not fetched or verified.

Supported query parameters:

- `search`: trimmed literal, case-insensitive substring of name or abbreviation.
- `conference`, `division`: exact saved current names, comma-separated OR within
  a field; different filters combine with AND.
- `ordering`: comma-separated `name`, `abbr`, `nhl_id`, `conference`, `division`,
  with `-` descending. Default `name,nhl_id`; strings use case-insensitive ordering
  and NHL ID breaks final ties. Metadata reports the requested/default ordering.
- `page`, `page_size`: positive integers, defaults 1/50, maximum size 100.

Filters and ordering run before pagination. An empty first page returns 200 with
count 0, empty results and null next/previous; other out-of-range pages return 404.
The list uses one read query regardless of returned team count. The saved team set
is filtered/sorted in Python; it is not presented as a historical metadata archive.

## Team detail and season selection

`GET /api/v1/teams/{nhl_id}/` accepts only optional canonical eight-digit
`season_id`, e.g. `20262027`. It returns:

```json
{
  "team": {
    "nhl_id": 7,
    "name": "Buffalo Sabres",
    "abbr": "BUF",
    "slug": "buffalo-sabres",
    "image_url": null,
    "arena_name": "",
    "arena_location": "",
    "division": "",
    "conference": "",
    "website_url": "",
    "nhl_debut": ""
  },
  "meta": {"season_id": "20262027"},
  "players_url": "/api/v1/teams/7/players/?season_id=20262027"
}
```

Omitting the season selects the newest loaded NHL regular-season SBS season across
both player types, including other teams. There is no calendar or team-specific
older-season fallback. A valid unloaded season stays selected. No loaded seasons
means null `meta.season_id` and no season query on `players_url`.

The linked contributions are paginated separately, so team detail never embeds
an unbounded roster. The link preserves the resolved season when known. A known
team remains available with empty player statistics. Team names, slugs, arena,
conference and division are current saved metadata, not historical reconstruction.

An explicit season requires one team read; default discovery adds two SBS reads.
Missing teams, zero or oversized integer IDs return JSON 404 without overflowing
the database integer column. Negative/non-numeric paths use the API JSON 404.

## Team player contributions

`GET /api/v1/teams/{nhl_id}/players/` returns the same paginated shape, typed
statistics and filters as the Players catalogue **except the `team` parameter is
not accepted**: the path defines the team. Defaults are skaters/totals; goalie
requests use `player_type=goalie` with totals/rates. Goalies reject averages.

`meta` includes `season_id`, `player_type`, `mode`, `ordering`, and the team's
`nhl_id`, `abbr`, `name`, `slug`. Entries reuse public catalogue identity, biography,
media, nullable fields and discriminated statistics, adding nullable
`jersey_number` from current profile data. Position filters likewise classify the
current profile; they do not reconstruct historical positions or jersey numbers.
Use named position filters to select split groups, or omit them for joined skaters.

Membership requires a matching NHL regular-season SBS row for the exact team and
season, with positive known integral games. PostgreSQL JSON containment narrows
candidates by team abbreviation; the reader checks the season and split. Current
roster foreign keys, stale snapshot fields, combined-only `TOT`/`nTM` rows, other
seasons and other teams cannot substitute for a missing split. Malformed/ambiguous
rows are excluded, not filled with overall season totals. Blank or combined saved
team abbreviations yield an empty contributions list rather than guessed membership.

A traded player's four COL games/one goal and six BUF games/three goals therefore
appear separately. BUF skater averages divide by six, not ten; goalie rates come
from the exact saved team row. By contrast, `/api/v1/players/?team=BUF` selects
season participants while retaining their overall totals. A scoped entry's `teams`
contains only the requested team. Null, zero, fraction and per-game TOI seconds
follow the catalogue contract. No freshness timestamp is invented.

Filtering/ordering precedes pagination, and statistics filters use the scoped
values. Missing values sort last both ways; last name/NHL ID break ties. A known
team with no matching contributions returns empty page 1; later pages return 404.
Two queries serve explicit-season requests (team plus selected player type), four
with default discovery. There is no per-player query growth. Only page entries
are serialized; raw histories, snapshots and private memberships remain deferred.

## Validation and regression evidence

Unknown, duplicate, blank, malformed or inappropriate query parameters return
typed JSON 400 before team/database lookup. All routes support GET/HEAD, JSON-only
negotiation and no-store responses identical for anonymous and signed-in viewers.
Unsupported methods return 405, HTML negotiation 406. OpenAPI describes all three
routes, filters, typed responses and errors.

Synthetic PostgreSQL regressions extend the existing season/trade fixtures. They
cover metadata and links, defaults, historical/empty seasons, skater/goalie splits,
combined-row exclusion, missing fields, filters/order/pagination, invalid IDs,
private boundaries, read-only execution and bounded queries with larger populations.
