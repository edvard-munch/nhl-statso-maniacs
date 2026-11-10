# Favorites API

The session-private Favorites API reads stored season statistics and changes explicit
membership. Existing HTML/AJAX favorites remain available with their existing POST
toggle contract. No migrations, new dependencies or frontend changes are required.

## Routes

| Method and route | Result |
| --- | --- |
| `GET /api/v1/me/favorites/` | Paginated saved players for the current account |
| `PUT /api/v1/me/favorites/{player_type}/{nhl_id}/` | Add explicitly: 201 created, 200 already present |
| `DELETE /api/v1/me/favorites/{player_type}/{nhl_id}/` | Remove explicitly: 204, including already absent |

`player_type` is `skater` or `goalie`; NHL IDs are positive signed-32-bit integers.
Invalid types/ranges return 404. PUT requires an existing player (404 otherwise).
DELETE also succeeds when a valid typed player no longer exists.

All routes require an authenticated Django session; anonymous requests return
403 `authentication_required`. Responses are private/no-store and vary on Cookie.
PUT/DELETE require CSRF using the [session bootstrap contract](session-auth-api.md).
They accept an empty body or empty JSON object, and no query parameters. Owner IDs,
toggle flags and other body fields are rejected. No bulk reset is exposed here.

## List and statistics

Use the [Players query contract](players-api.md) for `player_type` (default skater),
`season_id`, `mode`, named filters/order and pagination. Goalies support totals only.
The default season is the latest valid loaded SBS season across the application.
The response contains `count`, `next`, `previous`, `results` and `meta`.

Unlike the public catalogue, saved identities remain visible with missing,
unverified or zero-game season statistics unless a filter excludes them. An empty
loaded-season catalogue produces `meta.season_id: null` and retains saved identities.
An explicitly selected season with no rows also retains them. Missing or ambiguous
statistics are `stats: null`, with `availability: missing|unverified`; complete and
partial packets use the nullable [profile statistics contract](player-profile-api.md).
Snapshot fields never substitute for selected-season data. Teams describe verified
selected-season participation; unavailable packets have an empty teams list.

Numeric range filters exclude unknown values. `*_isnull` filters select unknowns
explicitly. Unknown values sort last in either direction. Typed IDs distinguish
skaters and goalies even if their NHL IDs coincide. Private notes, comparison
membership and other accounts' data are not included.

`meta` contains resolved `season_id`, `player_type`, `mode`, `ordering` and `quota`:

```json
{
  "limit": 100,
  "skaters_count": 3,
  "goalies_count": 1,
  "total_count": 4,
  "remaining": 96,
  "over_limit": false
}
```

Quota counts both **unfiltered** favorite groups, independently of page, filters or
selected player type. PUT returns `player_type`, `nhl_id`, `is_favorite: true` and
the same quota object. DELETE has no response body.

## Quotas and concurrency

A new addition at the shared 100-player limit returns 409
`favorites_quota_exceeded` without changing membership. Repeating PUT for an
existing favorite returns 200 even at or above the limit. Existing over-limit data
is retained; removal remains possible and `remaining` is clamped to zero.
Comparison membership and other accounts are preserved.

Reads and writes hold the same transactional owner-row lock as legacy saved-list
writers. List projection and response serialization happen inside that lock so
rows and quota describe one membership snapshot. GET changes no domain records;
it can briefly wait for a writer. The list uses a bounded number of queries rather
than one query per player. Independent owners do not share a lock.

The lock serializes cooperating API and legacy writers; direct SQL or new writers
must also respect that contract. Responses describe state when the lock was held,
not a revision protocol: a future frontend must handle responses arriving out of
order. Idempotent PUT/DELETE makes retrying an intended state safe.

## Remaining work

Aggregated favorite gamelogs are a separate API slice. Comparison membership,
private notes/positions and account settings also remain before Vue/Vite work.
No NHL calls or application database changes are needed to run the offline tests.
