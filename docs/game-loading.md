# Game-loader request failures and reruns

`upd_gms` now uses one checked JSON-fetch boundary for schedules, boxscores,
right-rail report links and play-by-play. The reported empty/HTML response no
longer escapes as a raw `JSONDecodeError`.

## Request behavior

- Each request uses the supplied session and a 10-second timeout.
- Empty/invalid JSON, non-object JSON, missing required fields, connection errors,
  timeouts, HTTP 408/429 and server errors receive up to three attempts, separated
  by exponential backoff (one/two seconds, or five/ten for HTTP 429).
  `Retry-After` seconds/dates can extend that wait; a requested wait over sixty
  seconds ends the request instead of retrying early. A successful retry returns normally.
- Other HTTP client errors, including 401/403/404, stop after one attempt.
- Responses are checked for HTTP errors before decoding. Schedules require their
  game-week and season-boundary fields; boxscores require state and home/away team
  fields. These are basic shape checks, not a complete schema validator.
- A failed required response raises `CommandError` with the date or game ID,
  endpoint URL, attempt count and cause. Gameday processing adds the day's date.
  Failed JSON requests are not converted into empty report data.
- Valid empty right-rail/play-by-play objects retain the existing missing-data
  fallback behavior. Optional HTML reports also retry transient failures; persistent
  429 raises an error while other unavailable HTML retains the existing fallback.

The shared retry limits are named constants in `players/nhl_http.py`; see
[loader HTTP policy](loader-http.md). A timeout applies to each attempt,
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
loading the missing player and replaying can complete that roster. Corrected
participants and conservative gamelog cleanup are covered below, along with
opposing-player sweater collisions.

## Malformed supplied rosters

For active/finished games, `upd_gms` validates supplied rosters before fetching
supplemental reports or updating game/player records. Both sides must contain
`forwards`, `defense` and `goalies` lists, without additional roster groups. Each
entry must be an object with a positive player ID and a position compatible with
its group. Integer and numeric-string IDs share one identity; duplicates within
or across sides are rejected. A side with all three lists empty is rejected;
an individual empty list is allowed.

Goalies require a string TOI in the existing minute/second format so missing TOI
cannot silently mean bench status. Played goalies also require `goalsAgainst`.
This is a roster structure/identity boundary, not validation of every numeric stat.

A malformed supplied roster raises `CommandError` identifying the gameday, game,
boxscore URL and invalid roster path. The existing per-day transaction restores
games, roster links, sides, player gamelogs and completion flags, including updates
made for earlier games on that day. After fixing the response, replay the same
command; regression tests check repeated two-game replay without duplicate records.

An absent, null or empty-object roster retains the existing pending-game behavior:
previous player logs/links stay intact and finished flags clear. The legacy nested
`boxscore.playerByGameStats` format remains supported. Scheduled/pregame responses
do not require rosters. No existing games are scanned or changed automatically.

## Corrected participants and gamelog cleanup

Reloading a valid supplied roster reconciles all six roster groups. A removed or
replaced skater/goalie loses only the verified gamelog entry for that game/date.
A goalie corrected to zero TOI loses the played appearance; a player moving
position or side retains an updated appearance. Older history, season/career
fields and favorites/comparison memberships remain intact. An unknown replacement
still leaves the game pending under the existing missing-player rule.

Newly loaded gamelog entries include `gameId` alongside their existing player,
team and opponent metadata. Cleanup considers only players previously linked to
this game who are absent from the refreshed played roster. A tagged entry must
match both game and player IDs. For legacy entries without a game ID, cleanup
requires matching player identity and both stored game teams, with no other
same-date game linking that player. Skater and goalie database IDs remain separate.

Conflicting IDs, malformed metadata and ambiguous same-date entries are retained
with a `Retaining unverified gamelog` warning. The game roster links still update
to the supplied roster. Missing/unavailable rosters preserve existing links/logs;
malformed supplied rosters fail before cleanup. Cleanup and new player writes
share the gameday transaction, so a later failure restores removed logs and links.
Repeated successful reloads preserve IDs and history.

This behavior takes effect when a game is reloaded; it does not scan historical
data or recover orphaned logs whose game links were already removed by earlier
loader runs. No database schema migration is required for the JSON marker.

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

## Audit previously loaded TOI (read-only by default)

The parser fix does not change saved data. Audit a single known game first, then
expand to a season or an inclusive date range:

```bash
python manage.py audit_game_toi --game-id 2026020232
python manage.py audit_game_toi --season 20262027 --output /tmp/game-toi-audit.jsonl
python manage.py audit_game_toi --start-date 2026-10-01 --end-date 2026-11-05
python manage.py audit_game_toi --season 20262027 --json > /tmp/game-toi-audit.json
```

Use your normal application database configuration: this command deliberately
reads saved games and player gamelogs, but performs no database writes. It makes
live NHL requests, unlike the mocked offline tests. No deleting records, resetting
completion flags or running the updater is necessary to audit. Database writes
require the explicit `--repair` option described below.

`--season` accepts an eight-digit ID and selects regular-season game IDs. Date
filters and repeated `--game-id` arguments can narrow the selection; filters
combine as intersections. A season, game ID or both date bounds are required.
Only saved games marked `game_finished=True` are scanned by default, so scheduled
future games are excluded without fetching their boxscores. Use
`--include-unfinished` to inspect games whose local completion flag may be stale;
the source must still be final. The command does not discover missing games.

The audit checks source game ID/date and final state, then compares each played
player's `powerPlayToi` and `shorthandedToi` against their saved date-keyed gamelog.
Home/away TOI reports are mapped separately by jersey to NHL player IDs. Existing
boxscore values take precedence, matching the loader. Equivalent time strings
such as `0:00` and `00:00` compare equally. Unused backup goalies are excluded.

A rostered skater may have explicit zero total `toi` in the boxscore and no
individual TOI report block. In that case, otherwise missing PP/SH fields are
verified as `00:00`, with source `boxscore_zero_toi`. Missing, malformed or positive
total TOI does not establish zero special-teams time. Existing boxscore/report
PP/SH values retain their normal precedence. The same evidence can repair a wrong
or missing saved PP/SH value under `--repair`; already-zero fields need no write.
This does not change loader behavior or the exclusion of unused backup goalies.

- `match`: the saved field agrees with the current source.
- `mismatch`: a valid source value differs from the saved field (including a
  missing/invalid saved field). The output includes game/date/player, field,
  stored and expected values, and source.
- `unverified`: source data is unavailable, invalid or missing; the game is not
  final; its identity/date differs; or a saved player/gamelog cannot be resolved.
  Missing reports never become expected zeroes. Ordinary failed games do not stop
  the remaining audit; persistent rate limiting stops the run as described below.

Default output lists mismatches/unverified records plus a summary. `--json` emits
one JSON object with `summary` and all `records`, including matches. Summary status
counts refer to records/fields, not games; separate counters identify games with
mismatches or unverified records (a game can belong to both). Zero selected games
means nothing was audited. Findings do not cause a nonzero exit status; review the
summary rather than treating process success as proof of clean data.

### Progress, rate limits and resuming

Progress is always written to **stderr**, including game index/total, date, NHL ID,
cumulative mismatch/unverified game counts, elapsed time and retry waits. It stays
visible when `--json` stdout is redirected. The final progress line identifies the
checkpoint location (or stdout when no file was requested).

All audit HTTP requests, including HTML reports and retries, are paced at least
one second apart by default. Override with `--request-delay 2` for a slower run.
HTTP 429 responses get at most three attempts, with 5/10-second exponential waits
and a longer `Retry-After` delay when supplied (seconds or an HTTP date). If the
server requests more than 60 seconds, the audit stops instead of retrying early.
Persistent 429 responses mark the current game unverified and stop before the next
game, avoiding a season-long retry loop. The audit retains its own pacing and
checkpoint behavior; normal loaders now also have [shared cooldown handling](loader-http.md).

Use `--output` for an **incremental JSONL checkpoint**, separate from the optional
final JSON stdout report. The file starts with a version/selection header, followed
by one flushed JSON object per completed game. It remains usable after Ctrl+C or
process termination. Existing files are never overwritten by a new audit.

```bash
# Start a new report; progress remains visible in the terminal.
python manage.py audit_game_toi --season 20262027 --output /tmp/game-toi-audit.jsonl

# After interruption or rate limiting, resume with exactly the same selection.
# Request pacing can be changed without invalidating the checkpoint.
python manage.py audit_game_toi --season 20262027 --output /tmp/game-toi-audit.jsonl \
  --resume --request-delay 2 --json > /tmp/game-toi-audit.json
```

Resume skips games with verified results (including known mismatches), retries
unverified games and visits newly selected saved games. A retried game's latest
checkpoint record replaces earlier results in the final summary/JSON report;
the JSONL journal retains both entries. A partially written final line is discarded
and that game is retried. Invalid complete records or a different selection/version
are rejected. Use one process per checkpoint; do not resume a file while another
process is still writing it.

Checkpoint results describe the database and sources at the time each game was
audited. **After repairing data, start a new output file** to recheck those games;
resume intentionally reuses verified findings. The old single-object `--json`
stdout report is not a resumable checkpoint. Without `--output`, stdout is still
written at the end; there is no durable incremental file.

Ctrl+C and rate-limit stops produce a partial final summary/report and a nonzero
exit status. Completed checkpoint entries survive; an interrupted current game is
retried on resume. Ordinary mismatches/unverified findings retain the existing
zero-exit behavior, so always review the summary.

This audit covers special-teams TOI only, using the current parser and current NHL
responses. It does not independently validate that parser, audit other game stats,
or infer when a bad value was originally saved. Review unverified games separately
before planning targeted repair/backfill.

## Targeted repair of verified PP/SH mismatches

Use `--repair` with the same game/season/date selectors. This explicitly enables
database writes; without it the command remains read-only. Start with the known
game, then cover the range you reviewed. Keep a database backup before a bulk repair.

```bash
python manage.py audit_game_toi --game-id 2026020232 --repair \
  --output /tmp/game-toi-repair-2026020232.jsonl

python manage.py audit_game_toi --season 20262027 --end-date 2026-11-02 --repair \
  --output /tmp/game-toi-repair-season.jsonl --request-delay 2

# Resume the repair, retaining exactly the same selectors and repair mode.
python manage.py audit_game_toi --season 20262027 --end-date 2026-11-02 --repair \
  --output /tmp/game-toi-repair-season.jsonl --request-delay 2 --resume
```

The command **fetches fresh sources** before repairing each game. It does not
import expected values from the old JSON report. Only verified mismatches in
`gamelog_stats[date].powerPlayToi` and `shorthandedToi` are patched. Genuine source
zeroes can replace wrong values. Unverified fields, missing players/gamelogs and
ambiguous identities are left untouched; valid fields in a partially unverified
game can still be repaired. A source rate limit stops the game before any patches.

Network requests finish before the per-game write transaction. The day, game and
player rows are locked, identities/dates are checked again, and each candidate
field must still equal the stored value observed by the fresh audit. A concurrent
TOI edit becomes a conflict rather than being overwritten; a value already corrected
is recorded as such. Unrelated edits, other gamelog dates/statistics, season/career
statistics, player metadata, rosters, memberships and completion flags are preserved.
Duplicate repair evidence is rejected. Database failure rolls back every patch
for that game and stops the run; earlier committed games remain repaired.

Repair records keep the pre-repair `stored` and fresh `expected` values, plus a
`repair` result: `applied`, `already_correct`, `conflict`, or `failed`.
`mismatch` counts still describe the comparisons **before** repair. Additional
summary fields `repaired`, `already_correct`, `repair_conflicts` and `repair_failed`
count repair outcomes. Inspect conflicts/unverified fields even when the command
finishes successfully. Database failures, interruption and rate limits produce a
nonzero exit status.

Use a **new checkpoint path for repair**. Read-only checkpoints cannot be resumed
as repairs (and repair checkpoints cannot be resumed as read-only audits). On repair
resume, games with unverified fields, conflicts or failed saves are re-audited;
verified completed games are skipped. Latest per-game results replace previous
results in final summaries, so `repaired` counts describe the latest records, not
a lifetime total across retries. The JSONL journal preserves the previous entries.
If interrupted after a database commit but before writing its checkpoint, a resumed
fresh audit sees the already-correct fields and does not patch them again.

Finally, verify with a **new read-only audit**, without `--resume`:

```bash
python manage.py audit_game_toi --season 20262027 --end-date 2026-11-02 \
  --output /tmp/game-toi-verification.jsonl --request-delay 2 \
  --json > /tmp/game-toi-verification.json
```

Previously unverified fields still need separate investigation; a successful repair
is not proof that every source field was available or every other game stat is correct.

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
