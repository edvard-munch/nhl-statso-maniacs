# Comparison API

The session-private comparison API keeps the current account's skater and goalie
selections separate. It supports season and career statistics without changing
existing HTML/AJAX comparison workflows.

## Routes and authentication

| Method and route | Result |
| --- | --- |
| `GET /api/v1/me/comparison/` | Paginated typed selection with statistics and quota metadata |
| `PUT /api/v1/me/comparison/{player_type}/{nhl_id}/` | Add explicitly: 201 created, 200 already selected |
| `DELETE /api/v1/me/comparison/{player_type}/{nhl_id}/` | Remove explicitly: 204, including already absent |
| `DELETE /api/v1/me/comparison/{player_type}/` | Clear only that typed group: 204, including already empty |

`player_type` is `skater` or `goalie`. NHL IDs are positive signed-32-bit integers;
invalid types/ranges return 404. PUT requires a saved player (404 otherwise).
Individual DELETE succeeds even when a valid typed player no longer exists.
Group DELETE never clears the opposite player type or Favorites.

All routes require a Django session; anonymous requests return 403
`authentication_required`. Responses are private/no-store and vary on Cookie.
Mutations require CSRF using the [session bootstrap contract](session-auth-api.md),
accept an empty body or empty JSON object, and reject query parameters or body
fields. There are no GET mutations or toggle operations in this API.

## Season and career statistics

`player_type=skater`, `scope=season`, and `mode=totals` are defaults. Use the
[Players query contract](players-api.md) for filters, ordering and pagination.
Goalies support totals only, with their rates included in that packet.

- `scope=season`: `season_id` selects canonical NHL regular-season SBS data;
  omission selects the newest valid loaded SBS season across the application.
  Missing/unverified/zero-game members remain unless a filter excludes them.
  With no loaded seasons, `meta.season_id` is null and saved identities remain.
- `scope=career`: saved `career_stats` or skater `career_stats_avg` feeds the
  [profile statistics contract](player-profile-api.md). `meta.season_id` is null
  and `teams` is empty. `season_id` and `team` filters are rejected rather than
  silently ignored. Career values are never inferred from season rows or snapshot
  columns; missing career data remains null. Invalid individual career values are
  null according to the existing profile projection policy.

Numeric filters/order use the chosen scope and mode. Unknown values sort last
in either direction; ranges exclude unknowns and `*_isnull` selects them explicitly.
Selected-season teams describe verified participation, not a current-team guess.
Public identity and nullable statistics are explicit allowlists. Notes, position
overrides and other accounts' saved state are not included.

The response contains `count`, `next`, `previous`, `results` and `meta`. Metadata
includes `season_id`, `player_type`, `scope`, `mode`, `ordering` and `quota`:

```json
{
  "limit_per_type": 5,
  "skaters": {"count": 3, "remaining": 2, "over_limit": false},
  "goalies": {"count": 1, "remaining": 4, "over_limit": false}
}
```

Counts describe both **unfiltered** typed selections, independently of pagination,
filters or scope. Each group has its own five-player quota. PUT returns
`player_type`, `nhl_id`, `is_compared: true` and the quota object. DELETE returns
no body. Skater and goalie IDs are distinct typed identities even when equal.

## Quotas, retry behavior and concurrency

A new addition to a full typed group returns 409 `comparison_quota_exceeded`
without changing membership. Repeated PUT returns 200 even when that group is
already at/above quota. Existing over-limit selections are preserved, with
`remaining` clamped to zero. Removal/reset still work; the other type's capacity
is independent.

All list reads, membership checks, quota checks, writes, resets and response
serialization run under the existing transactional owner-row lock. Legacy
comparison toggles/resets use that same lock, so competing requests cannot
consume the final slot twice. Unrelated accounts do not share a lock. GET makes
no domain writes and calls no NHL endpoints; it can briefly wait for a writer.
Queries are bounded rather than issued per selected player.

Direct SQL or new writers must also respect the owner-lock contract. Response
metadata describes state at serialization time, not a revision protocol. A future
frontend must handle responses arriving out of order and clear private state on
account change. Repeating a typed group reset intentionally clears the group
again, including selections added since the previous reset.

## Remaining work

The [aggregated Favorites gamelog](favorites-gamelog-api.md) is implemented.
[Private notes/positions](private-player-data-api.md) are also implemented.
Account settings/uploads and search APIs precede Vue/Vite scaffolding. No migrations,
new dependencies, application DB changes or frontend implementation are required
for this API slice.
