# API conventions for the frontend migration

Recorded: 2026-11-09. These are **target contracts for new `/api/v1/` endpoints**.
The [foundation below](#implemented-api-foundation) and
[saved scoreboard resource](scoreboard-api.md) are implemented. Other statistics,
account and saved-list endpoint families remain future migration work. Existing
pages and legacy AJAX responses retain their contracts until a tested replacement
is switched in. The [architecture plan](frontend-architecture.md) records the order.

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


## Implemented API foundation

The locked runtime now includes DRF 3.18.3 and drf-spectacular 0.30.0. The legacy
`typing_extensions` 4.5.0 pin is updated to 4.16.0 because schema validation's
import path fails on Python 3.12 with the older version. Django/Python and other
existing locked package versions are unchanged; the schema tools add their own
transitive dependencies. Install the updated runtime with `uv sync --locked`.
No application migration is introduced.

| Route | Current behavior |
| --- | --- |
| `GET /api/v1/` | Session-authenticated, private/no-store version metadata: `{"version":"v1"}`. Anonymous access returns JSON 403 `authentication_required`. This is not a service-health probe. |
| `GET /api/v1/schema/` | Public read-only OpenAPI 3.0.3 JSON. Only implemented operations are described; no YAML, Swagger UI or browsable API is served. |
| `GET /api/v1/games/?date=YYYY-MM-DD` | Public saved scoreboard JSON, with strict query validation, nullable verified legacy scores, pagination and freshness. See [resource contract](scoreboard-api.md). |
| Unknown/slashless `/api/v1` paths | JSON 404, without a trailing-slash redirect or unsafe-request replay. |

Public schema serving performs no database queries or upstream requests. Generate
and validate the same contract offline, after configuring normal Django settings:

```bash
uv run --locked python manage.py spectacular --format openapi-json \
  --validate --fail-on-warn --file /tmp/nhl-api-schema.json
```

The normal offline suite runs this validation and fails on schema warnings. Schema
artifact/client regeneration checks arrive in their later migration phase; there
is no generated frontend client yet.

New DRF views inherit JSON rendering/parsing, session authentication and
`IsAuthenticated` by default. Public reads must explicitly opt into `AllowAny`.
Session CSRF errors are distinguished from authentication/permission errors;
existing session-backed and HTTP-only CSRF configurations remain supported. No
JSON login/CSRF bootstrap or account endpoints are implemented yet; the
[saved scoreboard](scoreboard-api.md) is the first statistics resource.
The existing HTML login continues to establish sessions during this transition.
Future uploads must deliberately enable their multipart parser rather than
loosening parser policy globally.

The API boundary normalizes Django/middleware failures as well as DRF exceptions,
including debug-mode errors. API errors have private/no-store cache headers;
Allow/Retry-After and relevant security headers survive normalization. Unexpected
failure details are logged, while the response uses a generic server-error message.
Every Django-served API response carries a server-generated `X-Request-ID`, also
bound to diagnostic logs. Incoming request IDs are not trusted as the local ID.
Proxy-generated errors/TLS redirects are outside Django's JSON response guarantee
and require deployment configuration. Routes outside `/api/v1/` retain their HTML
and error/CSRF contracts.

The existing coverage gate still measures `players`; foundation modules under
`nhl_web_app.api` have explicit contract tests but are not added to that percentage
by this commit. Extending coverage scope is a separate reporting decision.
