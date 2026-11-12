# Vue Favorites: private read foundation

`/favorites` reads the current signed-in account's saved players through the generated
[Favorites API](favorites-api.md). It is linked from home/main navigation and can be
a validated sign-in return destination. Normal development requires Django and Vite
as described in the [frontend instructions](../frontend/README.md); test fixtures
are not used by the running application.

This focused slice adds list reads, filtering/pagination, quota display and public
profile navigation. Add/remove membership, aggregated Favorites gamelogs, comparison
and private notes/positions are separate following commits. Existing Django saved-list
workflows remain available; no new mutation controls or backend behavior are added.

## Session and private data lifetime

The component-local `usePrivateRead` helper waits for a healthy authenticated session
and uses that session's API client. Unknown/loading, busy, anonymous or failed session
states do not issue private GETs. A visible sign-in prompt preserves the full applied
Favorites URL. An unavailable session requires the header's explicit **Check session**.

Accepted rows and quota belong to the captured account ID, session revision and route
key. Auth/check actions, identity/revision changes, route changes and unmount abort
pending reads and clear accepted data. Late results cannot restore a previous account
or query, including transports that ignore cancellation. Private packets are not kept
as last-good data, shared with public DTOs, persisted in browser storage or retained
in an application cache. The API's existing private/no-store response policy remains
unchanged. Backend session authentication remains authoritative for ownership; no
owner ID is supplied by the browser.

A private 403 immediately clears data and shows an explicit session-check action;
it does not assume anonymous identity or automatically loop checks/GETs. A check can
resolve to anonymous, unavailable or a verified account. A still-forbidden verified
account stays blocked until another explicit action. Session changes outside this
app are recognized through session discovery/checks or a server rejection; this
slice adds no cross-tab identity notification or owner-revision response protocol.

Reads share the ten-second deadline and suppress stale success/error responses.
Network/protocol/page errors show safe text and request references, clear old rows
and allow explicit retry/first-page/filter recovery. Unknown upstream bodies are
never displayed. Unmount stops session watching and clears data even after a
previous successful load. Favorites reads never invoke membership writes, loaders,
email or NHL services.

## Season statistics and membership

The selected season defaults to the API's globally latest loaded season and pins
its resolved ID in the URL only after an accepted authenticated read. An explicit
empty season remains selected. No global loaded season leaves null selection while
retaining saved identities; there is no calendar or snapshot fallback.

Unlike public Players, missing/unverified packets and zero-game players remain in
Favorites unless a filter excludes them. Missing stats/GP stay `—`, not zero, and
availability remains visible. Season participation teams are distinct from current
profile position/nationality. Skater totals/per-game averages and goalie totals/rates
use backend packets unchanged, with per-game TOI formatted as `mm:ss` and goalie
save fractions displayed as percentages. No player freshness timestamp is invented.

Quota comes directly from `meta.quota` and counts both unfiltered typed groups,
independently of current filters/page. Existing over-limit lists remain visible;
remaining capacity is not recalculated from displayed rows. An empty group/filter
result differs from a wholly empty saved list.

## Filters and navigation

Season/type/mode, literal name search, season team/position/nation codes, rookie,
birth-date bounds, all type-specific numeric bounds/missing-value filters, named
ordering and page size follow the API's query contract. Team/code choices and ranges
are not guessed from a page or borrowed from the public Players facets. TOI bounds
use seconds and save-percentage bounds use fractions (0–1). Zero/false filters are
retained. Invalid, repeated or owner-selection parameters fail before private reads.

Apply/sort resets pagination, while pagination/reload/back restore applied controls.
Type changes clear incompatible filters and goalie averages. Manual **Refresh Favorites**
re-reads saved data without polling or implying loader freshness. Wide tables stay
inside a labelled keyboard-focusable mobile scroll region.

Profile links carry the full applied Favorites route. Public profiles validate it
before offering **Back to Favorites**, while retaining team/catalogue return behavior.
A return after logout is gated again; public profile requests never receive private
filters or membership packets. Context contains navigation choices, not private rows
or quotas. Existing local-route/length validation applies. Server pagination URLs
are used only as availability flags; local routes preserve selections.

## Verification and next slice

Synthetic unit/component and intercepted desktop/mobile Chromium checks cover
anonymous gating, exact sign-in/profile returns, missing/zero/unverified members,
null/empty seasons, quota semantics, filters/page state, 403 checks without loops,
session failures, account switches, logout, late results, disposal and deadlines.
No application database, real accounts, email, loaders or NHL calls are used.

Next add explicit Favorites PUT/DELETE actions with CSRF, owner/revision boundaries,
quota handling and reconciliation of uncertain responses, extending this private
read foundation rather than adding private state to public API responses.
