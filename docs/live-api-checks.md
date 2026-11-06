# Optional live NHL API checks

Run from the project root using the locked environment:

```bash
make test-external
```

This is an explicit network check, separate from `make test`, coverage, commit/
push hooks and normal GitHub CI. It selects only the two `tests_external_api_*`
modules and the `external` marker, excludes browser tests and stops at the first
failure. The 22 cases make read-only GET requests; they never invoke publication
commands, request Django database fixtures or read/write application records.
pytest-django's normal database blocker remains in effect. Normal Django settings
still need the local environment described in [testing](testing.md).

To check collection without making any NHL requests:

```bash
uv run --locked python -m pytest -c players/tests/pytest.ini -m external \
  players/tests/integration --collect-only
```

## Reference data and contracts

The live fixtures deliberately use completed regular season **2023–24** and game
**2023020001**, dated **2023-10-10**, instead of assuming the current season has
games or every player is still active. Representative players are Connor McDavid
(`8478402`) and Andrei Vasilevskiy (`8476883`). References live in
`players/tests/integration/conftest.py`; change the season/date/game coherently if
NHL eventually removes those archives. These checks do not establish that every
current-season player or every historical report is complete.

| Source | Checked contract |
| --- | --- |
| Current schedule-calendar | Team IDs, labels and usable season IDs, without a fixed team count. |
| Team registry | The production registry reader resolves representative abbreviations. |
| Schedule and boxscore | Reference game identity/state, sides and a roster accepted by the production validator. |
| Player landing | Skater/goalie identity, position and career/season containers. |
| Player reports | Production paginated readers for skater/goalie bios/summary, plus realtime, faceoffs and PP/SH TOI fields. Requests are scoped to one reference player and season. |
| Career reports | Aggregated skater realtime/faceoff/TOI and goalie summary readers return the fields career enrichment consumes. |
| Game sources | Right-rail links, Event Summary availability, faceoff/away/home TOI HTML parsing and special-teams points from play-by-play. |

Assertions check required fields, identity and usable parsed rows; JSON key order,
additional fields, mutable totals and exact player/team counts are not contracts.
Event Summary HTML does not supply player PP/SH point columns, so that source is
checked for an available report/table; PP/SH points are checked through the
production play-by-play parser. TOI/faceoff checks require nonempty parsed rows.

The retired `statsapi.web.nhl.com` schedule/boxscore/linescore and projection
response checks are removed. The later legacy retirement also removes
`upd_pls_proj` itself, preserving stored projection data and UI. See the
[legacy audit](legacy-audit.md) for the separate artifact/dependency review.

## Pacing and failures

A shared session spaces request starts at least one second apart, including retry
attempts, and permits only GET. The existing loader HTTP helpers retain their
timeouts, bounded retries and `Retry-After` handling; offline sleep patches do not
apply to external tests. Shared game/report fixtures avoid repeat downloads.

Timeouts, rate limits, unavailable archives and missing/changed fields are failures,
not skipped or expected-failure results. An optional loader response of `[]`/`None`
must not make its live contract silently pass. Read the failing endpoint/context,
wait for a rate-limit cooldown where appropriate and rerun deliberately; do not
loop the suite or weaken required fields to hide a failure. Additional upstream
fields alone are harmless. Network failures do not prove a local code regression;
use the deterministic mocked reader/parser tests to investigate.

Live success is a point-in-time smoke check. It does not replace mocked regression
coverage, database persistence tests, backups or a production loader run.
