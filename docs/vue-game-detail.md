# Vue saved game details

The frontend route `/games/{nhl_id}` reads the public `gameRetrieve` operation
through the generated SDK. Scoreboard cards now link to it. Existing Django game
pages and deployment routes remain unchanged. Run the backend and Vite as described
in the [frontend workflow](../frontend/README.md).

## Navigation and requests

Scoreboard links carry validated date/page return context in the browser URL.
“Back to games” restores that exact scoreboard selection; direct links use the
saved game's date when known, or plain `/games` for an undated game. Reload and
browser history work without storing an arbitrary redirect URL. Malformed context
is ignored. Context query parameters are never forwarded to the query-free game
API; requests contain only the typed NHL ID and cancellation signal.

Malformed/nonpositive/unsafe numeric route IDs show “Game not found” without a
request. The backend remains authoritative for saved identity/range lookups.
An API 404 is a missing-game state. Other API/network/proxy failures have a retry
button; JSON error references are retained where available and raw proxy HTML is
not shown. Changing the ID clears old results and aborts the previous read. Late
responses and reads finishing after unmount cannot replace the current view.

## Summary and roster statistics

The summary reuses the scoreboard's saved-state/score presentation: real zero is
zero, unknown is unavailable, and conflicting legacy evidence is explicit.
Storage update/staleness information remains separate from state observation.
No current clock, period, start time or NHL observation timestamp is invented.
A null schedule date stays unavailable rather than borrowing the current date.

Away/home forwards, defencemen and goalies use the API's exact roster membership
and order. Every group is explicit, including empty groups. Player keys include
type and NHL ID. Current profile position is not substituted for an unavailable
game position; sweater number also uses game-specific evidence only. Missing and
unverified rows retain the known player identity and availability label. Valid
partial fields remain visible without deriving missing statistics.

Skater columns include all saved game counts plus total/PP/SH TOI; negative
plus/minus is preserved. Goalie columns include decision, TOI, goals against,
saves, shots against, save percentage and shutouts. Numeric seconds format as
`MM:SS` with minutes allowed above 59: `754` becomes `12:34`, `3600` becomes
`60:00`, and known zero becomes `00:00`. Fractions format as percentages with one
decimal: `0.923` becomes `92.3%`, known zero becomes `0.0%`. Null remains `—`.
Percentages, decisions, points, shutouts and missing counts are not reconstructed
from other fields. These are game values, never season or profile totals.

Tables have captions, row/column headers and expanded abbreviation titles. On
mobile, wide statistics scroll within focusable regions, with sticky player
names; keyboard users can focus a region and use arrow keys. The page itself
stays within the viewport. This is a functional layout, not a visual redesign.
See the [backend game contract](game-detail-api.md) for verification/provenance and
[shared saved state](game-state-api.md) for observation limits.

## Verification and next slice

`make frontend-test` covers all skater/goalie field mappings, units, zero/null,
partial/missing/unverified rows, typed identity collisions, undated/empty games,
return context, invalid IDs, 404 versus retryable failures and request cancellation.
`make frontend-test-browser` exercises scoreboard/detail navigation, deep-link
reload, history/back context, mobile overflow/keyboard scrolling and error recovery.
Fixtures and Fetch interception keep both suites independent of application data
and NHL services. Existing frontend CI runs these checks and the production build.

Automatic saved-data refresh and interactive freshness handling are the next
focused slice. Player-profile links, saved-list mutations, styling framework and
production route cutover remain separate migration work. No backend schema,
loader, dependency, migration or coverage-scope change is needed here.
