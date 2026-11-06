# Favorites, comparison and the season-update workflow

Favorites and comparison use the same season reader as the Players table.
Selected-season totals come from `sbs_stats`; averages are derived from those
totals. Ordinary `goals`, `goals_avg`, `games` and similar snapshot columns, and
cached `sbs_stats_avg`, are not used as fallback season statistics.

## Saved lists

The default season is the latest valid NHL regular season loaded into SBS across
all players, as on the Players and team pages. An explicit `season=20262027` or
`season=2026-27` selection remains selected even when no statistics exist for it.
The season selector and AJAX requests use the same selection.

Unlike public Players/team tables, saved lists retain players without a matching
season row, including retired players. Their statistics display dashes and an
unavailable-season label. Zero-game rows remain visible with zero totals and
unavailable averages. Missing or malformed rows never fall back to older seasons
or snapshot columns. Numeric filters can still exclude unavailable values;
sorting keeps unknown statistics last.

Names, measurements and other identity fields come from current profile metadata.
Team labels come from the selected season; players with multiple season teams
show TOT. Comparison career modes read career aggregates independently of the
season selector. Missing career values display dashes. Legacy career key names
are accepted for existing records.

Favorites gamelog explicitly includes all stored seasons; the selector applies
only to season totals/averages. Its existing ordering behavior is unchanged.
Comparison removal/reset preserves the selected season and both statistics modes.
Saved memberships, per-type comparison limits, favorite membership and user
privacy remain intact. Rendering a different season never removes a saved player
or modifies player statistics. No schema migration is required.

## Saved-list requests

Favorite toggles (`player_favorite`), comparison toggles (`player_compare`) and
comparison resets (`reset_comparison`) require **POST**. GET and HEAD return 405
without changing memberships. Existing authentication responses, per-type limits
and ownership rules still apply.

The shared AJAX setup reads Django's masked CSRF token from the base template
and sends `X-CSRFToken` only to the same origin. Django rejects missing/invalid
tokens and untrusted origins with 403. This also works with HTTP-only or
session-backed CSRF cookies because JavaScript reads the DOM token, not the cookie.
Keep the shared setup loaded after jQuery and before the mutation controllers.

Season and statistics-mode selections remain URL query parameters on POST, so
removal/reset responses retain the selected table. Table reads, filtering and
statistics-mode switches remain GET requests. Favorite links generated for the
Players table use the canonical trailing-slash route to avoid POST redirects.

### Concurrent changes

Every saved-list toggle and comparison reset locks the account's user row inside
a database transaction before reading membership or counting quota usage. This
serializes changes for that account across requests and server workers, including
an initially empty list and favorites split across skaters/goalies. Other accounts
use different rows and can proceed independently. The transaction includes
comparison payload rendering, so a rendering failure rolls back the change.
See Django's [row-locking contract](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).

Favorites retain one shared 100-player limit; comparison retains separate
five-skater and five-goalie limits. Two additions competing for the final slot
produce one addition and one existing quota response. Removal remains allowed at
capacity. Two concurrent toggles of the same player run in order (add, then remove
if initially absent); toggles are not idempotent. Reset and toggle outcomes follow
their database lock order. Network responses can arrive in a different order.

New saved-list writers must use `players.saved_actions.locked_user` and perform
all membership reads and writes inside its transaction. Direct ORM/admin writes
can bypass this application-level quota policy. Existing over-limit data is not
trimmed automatically; additions are blocked until there is room, and removals
remain available. No migration is needed. Concurrency tests require PostgreSQL
and real committed transactions, rather than SQLite or a wrapping test transaction.

## Running updates

Manual commands below remain supported. Planned automatic live-game and batch
cadences are recorded in the [server scheduling policy](loader-scheduling.md);
game refreshes alone do not refresh these season/career tables.

From the repository root, activate the existing environment:

```bash
uv sync --locked
```

For a regular refresh:

```bash
uv run --locked python manage.py upd_tms
uv run --locked python manage.py upd_pls
uv run --locked python manage.py upd_pls_tot --mode=current
uv run --locked python manage.py upd_gms
```

Run `upd_tms` weekly; run the other commands frequently, typically daily.
In the locked uv environment, `make update-daily` runs players → current totals →
games; `make update-all` runs teams first and then the same sequence. Both stop
on the first failed command, retaining earlier completed loader updates. Full
historical refresh remains a separate explicit command.
`upd_pls` refreshes profile metadata and current season rows. Current totals mode
refreshes current season rows and career aggregates without player landing calls.
`upd_gms` supplies game logs; it is not the source of season table statistics.

For historical refresh/backfill, run occasionally:

```bash
make update-history
```

Full mode refreshes profile/career data through landing responses and historical
season/team rows through reports. It is useful when older rows or traded-player
team splits need rebuilding. See [loader details](season-statistics-loaders.md).
Do not clear saved lists or zero historical player statistics at season rollover.
After loading, select the new season and verify Players, a team, Favorites and
Comparison. A saved player absent from the new season should retain their identity
and display unavailable statistics. Career modes should still show career data.
Start the app with `uv run --locked python manage.py runserver`.

## Regression checks

Use Django's isolated PostgreSQL test database and real migrations:

```bash
uv run --locked python -m pytest -c players/tests/pytest.ini \
  players/tests/integration/tests_saved_season_tables.py \
  players/tests/integration/tests_players_season_table.py \
  players/tests/integration/tests_team_season_tables.py
node --check players/static/players/sorting_favorites.js
node --check players/static/players/sorting_comparison.js
```

These cover saved membership, stale snapshots, missing/zero-game seasons, totals
and averages, initial/AJAX parity, career aliases, anonymous/private access,
comparison removal/reset/limits, validation and query growth. Do not pass
`--nomigrations`: the legacy ImageField schema differs from migration state.

`tests_saved_player_actions_db.py` also checks GET/HEAD rejection, CSRF failures,
untrusted origins and valid POST persistence for both player types. Chromium
checks exercise the actual POST controllers, CSRF headers, membership transitions
and failure/retry behavior; `make test-browser` runs them separately.

Run `make test-cov` and `make test-ci` separately to assess the complete suite and
the initial 35% gate. Focused results do not establish full-suite coverage or fix
unrelated legacy collection/database-isolation problems. Optional live API checks
remain excluded by default.
