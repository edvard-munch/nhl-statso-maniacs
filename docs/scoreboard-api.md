# Saved scoreboard JSON API

`GET /api/v1/games/?date=2026-11-09` returns saved games for exactly that NHL
schedule date. This is a public, read-only resource: it does not start loaders,
contact the NHL, create missing gamedays, render templates or modify saved data.
The existing HTML scoreboard and its AJAX endpoint remain operational.

## Request and pagination

`date` is required and must be an actual calendar date written exactly
`YYYY-MM-DD`. It means the stored Pacific NHL schedule date, not midnight in the
viewer's timezone. There is no implicit today/latest-date fallback. A valid date
without saved games returns 200 with an empty list, even if other dates have games.

Optional `page` and `page_size` are positive integer strings. Page defaults to 1;
page size defaults to 50 with a maximum of 100. Unknown or repeated parameters,
invalid dates and invalid pagination values return a JSON 400
`invalid_parameters` with field errors. Page 1 may be empty; any other page beyond
the available result set returns JSON 404 `not_found`. Games are ordered by NHL
ID, independently of insertion order.

The response has `count`, `next`, `previous`, `results` and `meta`, following
[API conventions](api-conventions.md). Pagination links preserve the requested
date/page size. `meta.date` and aggregate freshness describe the entire requested
date, including games not displayed on the current page. The dated collection is
loaded with a team/side prefetch: a nonempty scoreboard uses two SELECTs, avoiding
per-game team queries. The collection is day-scoped; this is not an all-history feed.

## Game and team fields

Each game contains:

- `nhl_id`, `slug`, `date` and saved `is_final`.
- `away_team` and `home_team`: `nhl_id`, `name`, `abbr`, `slug`, or null when the
  relevant saved side is missing/duplicated. Side relations identify the teams;
  current player rosters are not consulted. Team names are current saved metadata.
- `away_score`, `home_score`, `score_outcome` and `score_source` as described below.
- `freshness` as described in the next section.

No rendered result labels, table cells, user/favorite information or internal
model dumps are returned. Anonymous and signed-in viewers receive the same data.
Responses currently use no-store headers so browser checks reach saved data;
future shared caching requires an explicit freshness policy. GET/HEAD are reads,
OPTIONS supplies normal API metadata, and unsupported writes return JSON 405.

## Conservative adaptation of legacy scores

There are no separate score columns in the current `Game` model. The endpoint
therefore adapts the **known loader-produced `Game.result` format**, without a
schema change or backfill:

1. Require exactly one saved away side and one home side with distinct NHL teams.
2. Require the exact saved team-name prefix, in away/home order.
3. Require the entire remaining string to be nonnegative integer scores `A:H`,
   optionally followed by the loader's ` (Live)`, ` OT` or ` SO` suffix.

A verified result returns integer scores, including genuine zero, and
`score_source: "legacy_result"`. `score_outcome` is `OT`/`SO` only if that suffix
is saved. Missing, malformed, reordered or unverifiable text returns null scores,
null outcome/source and `freshness.partial: true`. Renamed team metadata can also
make a previously saved label unverifiable; the API does not guess the old names.
A missing score never becomes zero, nor is it reconstructed from player statistics.

`is_final` comes from `Game.game_finished`, not the score string. False does not
prove that a game is currently live. Dedicated structured scores/state persistence
is a possible separate loader migration; this endpoint explicitly identifies its
legacy score source rather than claiming those fields already exist.

## Freshness

Both per-game and aggregate freshness contain:

| Field | Meaning |
| --- | --- |
| `has_data` | At least one matching saved game exists. |
| `is_final` | All represented games are marked finished; false for an empty date. |
| `saved_at` | Successful game-save timestamp, or null for an empty date. |
| `checked_at` | One shared UTC timestamp for this API request. |
| `age_seconds` | Nonnegative age of the selected save timestamp, or null. |
| `stale_after_seconds` | Existing 15-minute unfinished-game threshold. |
| `is_stale` | Unfinished saved data has reached the threshold; old finals are not stale merely because of age. |
| `partial` | Saved scoreboard team/score fields are missing or ambiguous. |

Aggregate save time is the oldest unfinished save, or the most recent save if all
games are final. Empty dates have null save/age values and false stale/partial
flags. Repeated checks advance check time without changing save time. These are
saved-state indicators, not NHL source timestamps or a guarantee that upstream
reports changed. Scoreboard `partial` does not assess player-statistics completeness.
The serializer omits the old helper's presentation text; the frontend supplies
its own labels and formatting.

## Schema and verification

The resource, query fields, pagination envelope, nullable values and error shapes
are declared in `/api/v1/schema/`. Normal API foundation tests validate/export the
schema without database queries or external requests. Endpoint regressions use
synthetic PostgreSQL games, the existing mocked loader fixture and guards against
HTTP calls, HTML rendering, writes and advisory/row locks.
