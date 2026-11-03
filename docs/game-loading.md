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
that repeating the tested scheduled-day load preserves game identity and does not
duplicate games or sides. Broader roster/gamelog orchestration contracts remain
follow-up work; a mocked passing test does not establish live endpoint availability.

## Regression checks

```bash
python -m pytest -c players/tests/pytest.ini \
  players/tests/unit/other/tests_upd_gms_requests.py \
  players/tests/unit/other/tests_upd_gms_reports.py
```

Using the [isolated PostgreSQL test setup](testing.md), also run:

```bash
python -m pytest -c players/tests/pytest.ini \
  players/tests/integration/tests_upd_gms_failures_db.py
```

Request tests cover recovered and exhausted retries, fail-fast client errors,
required JSON shape, session/timeout use and date/game/endpoint diagnostics.
Database tests exercise failure on a later boxscore, existing-day rollback,
right-rail/play-by-play failures, preservation of earlier days, and repeat loads.
All HTTP inputs are mocked; real migrations and an isolated test database are used.
