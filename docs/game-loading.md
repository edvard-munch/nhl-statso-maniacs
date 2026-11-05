# Game-loader request failures and reruns

`upd_gms` now uses one checked JSON-fetch boundary for schedules, boxscores,
right-rail report links and play-by-play. The reported empty/HTML response no
longer escapes as a raw `JSONDecodeError`.

## Request behavior

- Each request uses the supplied session and a 10-second timeout.
- Empty/invalid JSON, non-object JSON, missing required fields, connection errors,
  timeouts, HTTP 408/429 and server errors receive up to three attempts, separated
  by one second. A successful retry returns the response normally.
- Other HTTP client errors, including 401/403/404, stop after one attempt.
- Responses are checked for HTTP errors before decoding. Schedules require their
  game-week and season-boundary fields; boxscores require state and home/away team
  fields. These are basic shape checks, not a complete schema validator.
- A failed required response raises `CommandError` with the date or game ID,
  endpoint URL, attempt count and cause. Gameday processing adds the day's date.
  Failed JSON requests are not converted into empty report data.
- Valid empty right-rail/play-by-play objects retain the existing missing-data
  fallback behavior. Optional HTML report fetching and parsing are unchanged.

The limits are named constants in `upd_gms.py`. A timeout applies to each attempt,
not a strict wall-clock deadline for the entire command.

## Publication and replay

Each `process_games` call is a database transaction for one gameday. A required
response failure rolls back new/updated games, sides, player writes and completion
flags from that day's transaction. Previously committed days remain intact. API
fetches for the day occur inside that transaction; the whole season is not one
transaction.

Unavailable future-game payloads still produce a controlled failure. This change
does not introduce a policy for skipping/deferring those games. A failed day is not
marked complete. Once the endpoint is available, rerun:

```bash
python manage.py upd_gms
```

Existing command orchestration may revisit earlier days. Regression tests verify
scheduled and finished-game replays, updates to the same gamelog date, preservation
of older history and saved memberships, and rollback of player gamelogs when a later
game fails. Mocked schedule tests exercise a fresh database, existing pending days,
and live-to-final updates. Passing mocked tests do not establish live availability.

## Completion and roster contracts

A game is finished only when its state is `FINAL` or `OFF` and its played roster
matches stored players. `FUT`, `PRE`, `LIVE`, `CRIT` and `OVER` remain unfinished.
A matching live roster is not a reason to stop refreshing that game. Each successful
gameday refresh recomputes both completion flags, including clearing an earlier
finished flag when a roster is now missing/incomplete. The per-day transaction
preserves the previous state if the refresh itself fails. Existing completion
flags are corrected when those days are refreshed; this change does not scan or
backfill every stored day automatically.

The new database contracts check all six away/home roster groups and saved game
statistics. Existing HTML report fixtures are reused through real parsers, with
mocked right-rail/play-by-play responses. Boxscore zero/nonzero values take
precedence over enrichment; missing fields use report values and existing defaults.
Gamelog team/opponent identity comes from the game rather than the player's current
team foreign key. Bench goalies with zero TOI are excluded; shared shutouts are not
awarded as individual shutouts by the existing rule.

Missing database players leave the game/day unfinished and produce a warning;
loading the missing player and replaying can complete that roster. Follow-up
contracts should still cover removed participants/gamelog cleanup and malformed
roster groups. Opposing-player sweater collisions are covered below.

## Report player identity

Enrichment is combined and applied by NHL player ID. Play-by-play special-team
points retain their player IDs throughout; unknown/non-playing player IDs are
excluded. Integer/string identifiers are normalized consistently. A missing player
ID cannot fall back to a sweater number.

TOI reports are resolved against their explicit away/home roster, so two opponents
wearing the same number receive their own team's TOI. Bench goalies with zero TOI
are excluded from report identity resolution.

Event/faceoff HTML parsers still return unscoped jersey rows. Those rows are used
only when exactly one known played-roster player has that jersey across the game.
An ambiguous jersey is skipped with a warning identifying the report and game.
Existing boxscore values take precedence. Unassigned HTML fields retain the
existing fallback/default behavior, including zero defaults for missing counting
statistics; this does not recover ambiguous faceoff counts. Team/name-aware HTML
parsing can improve that separately without guessing another player's values.

Regression tests verify both opponents' saved special-team points and TOI, a
non-scoring opponent, boxscore precedence, repeat loads, nested roster layouts,
and unknown/missing identities. Existing gamelogs are corrected only when their
games are reloaded; this change does not automatically backfill historical games.

## Audit previously loaded TOI (read-only)

The parser fix does not change saved data. Audit a single known game first, then
expand to a season or an inclusive date range:

```bash
python manage.py audit_game_toi --game-id 2026020232
python manage.py audit_game_toi --season 20262027
python manage.py audit_game_toi --start-date 2026-10-01 --end-date 2026-11-05
python manage.py audit_game_toi --season 20262027 --json > /tmp/game-toi-audit.json
```

Use your normal application database configuration: this command deliberately
reads saved games and player gamelogs, but performs no database writes. It makes
live NHL requests, unlike the mocked offline tests. No deleting records, resetting
completion flags or running the updater is necessary to audit. There is no repair
option in this batch.

`--season` accepts an eight-digit ID and selects regular-season game IDs. Date
filters and repeated `--game-id` arguments can narrow the selection; filters
combine as intersections. A season, game ID or both date bounds are required.
Only saved games are scanned; the command does not discover missing games.

The audit checks source game ID/date and final state, then compares each played
player's `powerPlayToi` and `shorthandedToi` against their saved date-keyed gamelog.
Home/away TOI reports are mapped separately by jersey to NHL player IDs. Existing
boxscore values take precedence, matching the loader. Equivalent time strings
such as `0:00` and `00:00` compare equally. Unused backup goalies are excluded.

- `match`: the saved field agrees with the current source.
- `mismatch`: a valid source value differs from the saved field (including a
  missing/invalid saved field). The output includes game/date/player, field,
  stored and expected values, and source.
- `unverified`: source data is unavailable, invalid or missing; the game is not
  final; its identity/date differs; or a saved player/gamelog cannot be resolved.
  Missing reports never become expected zeroes. A failed game does not stop the
  remaining audit.

Default output lists mismatches/unverified records plus a summary. `--json` emits
one JSON object with `summary` and all `records`, including matches. Summary status
counts refer to records/fields, not games; separate counters identify games with
mismatches or unverified records (a game can belong to both). Zero selected games
means nothing was audited. Findings do not cause a nonzero exit status; review the
summary rather than treating process success as proof of clean data.

This audit covers special-teams TOI only, using the current parser and current NHL
responses. It does not independently validate that parser, audit other game stats,
or infer when a bad value was originally saved. Review unverified games separately
before planning targeted repair/backfill.

## Regression checks

### Overtime special-teams TOI

Player headings must contain a surname and given name separated by a comma,
with an optional position before the surname. Unicode letters are supported.
An overtime shift row such as `29 | OT | ...` is not a player heading: its number
is a shift number, not a jersey. Previously those rows interrupted the player's
block and could assign full-game PP/SH totals to a different jersey, or leave the
real player's values missing (subsequently defaulting to zero).

Reduced official reports from November 1, 2025 cover regulation (CAR), overtime
(COL and EDM), and a shootout (DAL). Fixtures preserve player headings, overtime
shift rows and full-game totals; each HTML file records its source URL. Tests
compare every reported player's totals, including goalies and accented names.
They also reject overtime shift rows as headings directly.

The fix affects report-derived `powerPlayToi` and `shorthandedToi`; boxscore values
still take precedence. Already stored gamelogs require replaying affected dates.
The normal updater may skip completed historical days; this fix does not perform
a historical backfill.

```bash
python -m pytest -c players/tests/pytest.ini \
  players/tests/unit/other/tests_upd_gms_requests.py \
  players/tests/unit/other/tests_upd_gms_reports.py \
  players/tests/unit/other/tests_upd_gms_identity.py
```

Using the [isolated PostgreSQL test setup](testing.md), also run:

```bash
python -m pytest -c players/tests/pytest.ini \
  players/tests/integration/tests_upd_gms_failures_db.py \
  players/tests/integration/tests_upd_gms_rosters_db.py \
  players/tests/integration/tests_upd_gms_report_identity_db.py
```

Request tests cover recovered and exhausted retries, fail-fast client errors,
required JSON shape, session/timeout use and date/game/endpoint diagnostics.
Database tests exercise failure on a later boxscore, existing-day rollback,
right-rail/play-by-play failures, preservation of earlier days, and repeat loads.
All HTTP inputs are mocked; real migrations and an isolated test database are used.

Latest full hook validation: **397 passed, 12 external tests deselected, 82.53%
combined coverage**. The roster/persistence module contributes 18 regression
cases; it initially exposed live-game and stale-day completion bugs, both repaired.

Report-identity follow-up: **407 passed, 12 external tests deselected, 82.59%
combined coverage** through the full offline coverage hook. The original three
collision cases failed before the fix and pass after it. No live NHL requests or
application database were used.
