# API conventions for the frontend migration

Recorded: 2026-11-09. These are **target contracts for new `/api/v1/` endpoints**,
not documentation of endpoints already implemented. Existing pages and legacy
AJAX responses keep their current contracts until a tested replacement is switched
in. The [architecture plan](frontend-architecture.md) records the migration order.

## Transport and resources

Use HTTPS in production and one public origin for frontend/API cookies. New API
routes use `/api/v1/`, plural resource names, trailing slashes and named query
parameters. Responses, including API validation/permission/CSRF/not-found errors,
are JSON. DRF JSON-only renderers alone do not cover Django/proxy errors outside
DRF; add API-scoped handlers and test relevant error paths. HTML views, redirects,
flash-message fragments and browsable-API rendering are not API responses.

Use snake_case JSON fields. Public NHL identities use `nhl_id` plus `player_type`
(`skater` or `goalie`); private/database primary keys do not substitute for typed
player identity. Include names/slugs/image URLs as data. The frontend builds page
links and labels; responses do not contain rendered cells, icons, tooltips or
HTML labels. Notes and other plain text are displayed with normal escaped Vue
interpolation rather than `v-html`.

Example endpoint families (introduce each in its own phase):

| Family | Purpose |
| --- | --- |
| `/api/v1/seasons/`, `/api/v1/players/` | Loaded seasons and public catalogue |
| `/api/v1/players/{player_type}/{nhl_id}/` | Typed profile; a gamelog subresource follows |
| `/api/v1/teams/`, `/api/v1/teams/{nhl_id}/` | Team identities and selected-season contributions |
| `/api/v1/games/`, `/api/v1/games/{nhl_id}/` | Date-scoped scoreboard and saved game details |
| `/api/v1/auth/...`, `/api/v1/me/` | CSRF/session lifecycle and account identity |
| `/api/v1/me/favorites/...`, `/api/v1/me/comparison/...` | Explicit saved membership resources |
| Private typed-player note/position subresources | Current user's validated overrides |

Endpoint serializers are explicit allowlists. Do not expose entire models,
internal JSON blobs, other users' data, or arbitrary ORM filtering/ordering paths.

## Statistics and units

- `season_id` is a canonical eight-digit string such as `20262027`. Omission on
  ordinary season lists selects the latest valid loaded SBS season, not today's
  calendar season. Return the resolved season in metadata. Invalid values are 400;
  a valid season with no matching rows returns an empty list for that season.
- `mode=totals|averages` selects backend-calculated values. Career endpoints/modes
  remain explicitly separate from selected-season data; define them when that
  workflow is introduced. Never replace missing season rows with snapshot fields
  or another season's values.
- Public catalogue membership, team contributions and saved-list missing-season
  behavior follow the existing [Players](players-season-table.md),
  [team](team-season-tables.md) and [saved-list](saved-player-season-tables.md)
  contracts. Current biography/measurements do not imply historical metadata.
- Known zero is `0`; unavailable values are `null`. Empty collections are `[]`.
  Expose availability separately where needed. Saved unknown values do not become
  zero merely for rendering or sorting.
- Counts are JSON integers, averages/ratios JSON numbers using existing backend
  precision rules. Document whether each percentage is a fraction or percentage;
  do not change units implicitly during serialization. Non-finite numbers must
  not escape as NaN/Infinity JSON.
- DTO adapters expose TOI/durations as numeric seconds with `_seconds` names;
  distinguish totals and per-game averages. Vue formats `MM:SS`. Preserve the
  existing rounding/derivation rules with parity fixtures before switching views.
- Timestamps use ISO 8601 UTC with `Z` or `+00:00`; dates use `YYYY-MM-DD`.
  NHL schedule dates remain Pacific schedule dates, not browser-local conversions.

Illustrative data shape, to be made authoritative through serializers/schema:

```json
{
  "player_type": "skater",
  "nhl_id": 8480000,
  "name": "Example Player",
  "slug": "example-player",
  "season_id": "20262027",
  "mode": "totals",
  "availability": "partial",
  "stats": {"games": 12, "goals": 0, "pp_toi_seconds": null}
}
```

## Lists, sorting and filters

Use page-number pagination: `page` and `page_size`, initially defaulting to 50
and capped at 100. Validate positive integers and reject unsupported filters,
modes and ordering fields with typed 400 errors. Endpoint-specific filters are
allowlisted/documented in OpenAPI before implementation; do not carry forward
positional column-number URLs or packed jQuery widget query strings.

The response has `count`, `next`, `previous`, `results` and `meta`. Counts describe
the filtered population before pagination. Empty results return count 0, null
navigation links and an empty results list. Define out-of-range-page behavior in
the first list contract tests. Include resolved `season_id`/mode and required
freshness/availability metadata rather than hidden template context.

Use `ordering=-points,last_name,nhl_id`-style named fields where applicable. Apply
filtering/sorting before pagination on the server; never sort only a fetched page
and present it as the whole ranking. Use deterministic identity tie-breakers,
including player type for mixed lists. Unknown statistics sort last in both
orders. Frontend URLs retain selected season, mode, filters and page.

## Authentication and writes

Use Django sessions with an HTTP-only session cookie and a JSON CSRF bootstrap
that works with session-backed/HTTP-only CSRF configurations. Protect login and
all unsafe session-authenticated operations; frontend separation is not a reason
to disable CSRF. Public endpoints explicitly allow anonymous reads; private
endpoints enforce authentication, ownership and permissions server-side.

For the session-auth API baseline, unauthenticated protected requests use DRF's
403 behavior with `authentication_required`; permission denials and invalid CSRF
also use 403 but distinct error codes. Do not assume SessionAuthentication returns
401 or conflate every 403 with session expiry. Invalid input is 400, absent or
non-disclosable resources 404, unsupported methods 405, quota conflicts 409, and
throttling 429 with Retry-After where applicable. Login failure details and field
responses are specified/tested with the auth endpoints, including enumeration
protection for recovery. Any later change to this mapping is an API contract change.

GET/HEAD never mutate application records or invoke loaders. Use explicit-state
membership PUT/DELETE operations in the new API: repeating add/remove must not
flip a previously successful result. Specify success bodies/statuses with their
serializers; delete succeeds with 204 even when membership is already absent.
Updates to notes/positions/account settings use validated PATCH/PUT as appropriate.
Legacy POST toggles remain untouched until their clients move.

All saved-membership checks/counts/writes remain inside
`players.saved_actions.locked_user`, including new idempotent paths. Preserve
100 combined favorites and five comparisons per player type; do not trim existing
over-limit data. Invalid/failed requests leave existing state intact. Do not add
blind retries to unsafe operations; test lost-response/repeated-request behavior
before configuring mutation retries.

Use private/no-store responses for account-specific data. Keep public statistics
responses independent of favorite flags/private text so shared SSR/public caches
cannot leak them. Clear private client caches on logout/account change and guard
against responses arriving after a newer selection or mutation.

## Errors, schema and freshness

Use a stable typed error envelope, for example:

```json
{
  "error": {
    "code": "invalid_parameters",
    "message": "Invalid request.",
    "fields": {"season_id": ["Use an eight-digit season ID."]}
  }
}
```

`code` is the client decision key; `message` is human-readable. Field errors are
optional. Internal failures use a generic message without traceback/secrets;
correlated application logs retain diagnostic details. Frontend screens render
loading/empty/error/permission states rather than showing raw HTML error bodies.

Freshness is saved-state evidence: expose save time separately from check time,
final/nonfinal status, staleness thresholds and saved-field availability. Preserve
[current game freshness semantics](celery-operations.md#browser-refresh-and-freshness),
including unknown supplementary fields and old final games. Public reads/polling
never start commands/Celery tasks or make upstream NHL calls.

The backend OpenAPI schema is authoritative for request/response shapes and
error/status variants. Generate clients reproducibly from a reviewed schema;
fix serializers/schema declarations rather than patching generated application
code. CI validates schema, regeneration drift, types and frontend production
build alongside backend tests. A breaking contract requires a coordinated client
change or a new API version, not a silent change under old consumers.

Contract tests cover data/units, zero versus missing, seasons, filtering/order,
pagination, JSON errors, CSRF/ownership, idempotence/concurrency and read-only
behavior. Browser tests cover public initial HTML/metadata, hydrated interaction,
account workflows, polling/recovery and preservation of user state. Template
assertions remain until their replacement workflow is tested and switched over.
