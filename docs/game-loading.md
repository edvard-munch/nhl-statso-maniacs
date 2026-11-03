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
contracts should still cover opposing players with the same sweater number,
removed participants/gamelog cleanup, and malformed roster groups.

## Regression checks

```bash
python -m pytest -c players/tests/pytest.ini \
  players/tests/unit/other/tests_upd_gms_requests.py \
  players/tests/unit/other/tests_upd_gms_reports.py
```

Using the [isolated PostgreSQL test setup](testing.md), also run:

```bash
python -m pytest -c players/tests/pytest.ini \
  players/tests/integration/tests_upd_gms_failures_db.py \
  players/tests/integration/tests_upd_gms_rosters_db.py
```

Request tests cover recovered and exhausted retries, fail-fast client errors,
required JSON shape, session/timeout use and date/game/endpoint diagnostics.
Database tests exercise failure on a later boxscore, existing-day rollback,
right-rail/play-by-play failures, preservation of earlier days, and repeat loads.
All HTTP inputs are mocked; real migrations and an isolated test database are used.

Latest full hook validation: **397 passed, 12 external tests deselected, 82.53%
combined coverage**. The roster/persistence module contributes 18 regression
cases; it initially exposed live-game and stale-day completion bugs, both repaired.
