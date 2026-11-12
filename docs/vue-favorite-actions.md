# Vue Favorites membership actions

Public player profiles now offer **Save to Favorites** for a healthy signed-in
account, or a sign-in entry preserving the profile URL. `/favorites` offers an
explicit **Remove from Favorites** button for each returned typed player. These use
the existing [Favorites PUT/DELETE contract](favorites-api.md); no backend, schema,
dependency, quota policy or public statistics payload changes are introduced.

There is no inferred favorite star or optimistic public membership flag. A profile
save is an explicit idempotent PUT even when the player may already be saved.
Removal uses explicit DELETE, including missing/zero-season members. The path
contains skater/goalie plus NHL ID, with no owner/query/toggle payload.

## Serialized account and CSRF boundary

The session store's `withPrivateAction` lease serializes saved-list writes with
login/logout, registration, recovery and session checks. Before writing it refreshes
CSRF/session discovery and verifies that the cookie identity still matches the
account that initiated the action. Unknown/unavailable/changed identity prevents
the write. The action uses an isolated client seeded with the verified CSRF token.

Header auth controls and additional membership buttons are disabled while a write
is running. Navigation remains available. App-owned progress/result state survives
row/view unmount; it does not depend on the clicked button remaining mounted.
Each network phase has the existing ten-second deadline: initial identity check,
write, and (only when needed) another identity check plus a single readback. A
client cancellation/timeout does not establish whether a server write committed.

The lease clears/invalidate private reads through session busy/revision boundaries.
After any completed attempt, current private views re-read their applied query and
server quota. Pending old GETs cannot overwrite post-action rows. Action feedback
and optional PUT quota snapshots are scoped to owner/revision and clear on later
session changes or app disposal. Public statistics DTOs remain independent. Backend
sessions and the owner-row lock remain authoritative; the client adds no owner-ID
parameter or cross-tab membership revision protocol.

## Confirmed and uncertain results

A matching PUT body with `is_favorite: true`, typed identity, a valid quota shape and
200/201 status yields explicit already-saved/added feedback. DELETE requires 204.
A quota rejection is displayed without changing the list locally. Full/over-limit
client counts never disable an idempotent save; the server decides whether the
particular addition is allowed. Removal stays available above quota.

A CSRF/authentication rejection refreshes session state but never repeats the
write. Correct the session and explicitly submit again if needed. Other known
request/player rejections show safe feedback; upstream bodies are not rendered.

Lost, timed-out, malformed or otherwise unconfirmed write responses may have
committed. After rechecking the same owner, the client requests one **unfiltered**
typed Favorites page at maximum page size. Season/search/statistic filters from the
visible table are excluded so missing/zero-season players cannot disappear from
membership verification.

A valid returned typed identity proves presence at that read. Absence requires a
complete first-page snapshot: null next/previous, distinct valid typed IDs and a
count matching the returned population. An incomplete legacy over-limit page cannot
prove absence. The client neither follows next URLs nor scans moving pages.

Observed desired state is reported as a saved-data observation with the original
response still described as uncertain. An opposite/incomplete/unavailable read stays
unconfirmed; no success or failure cause is invented. No PUT/DELETE is automatically
replayed, and a future action always requires another explicit click. Another writer
can change membership after a snapshot; readback is not a new revision protocol.

## Removal, quota and navigation

After removal, `/favorites` loads authoritative rows/quota rather than decrementing
local counts. If the initiating page becomes a 404 after confirmed or observed
absence, it returns to page one with the same filters/type/mode/season/page size.
It does not guess a new last page. A true empty list and an empty filtered group
retain their distinct messages. Unrelated bookmarked page failures retain normal
manual first-page recovery.

App-owned notices remain available after a removed row unmounts or the user
navigates to Favorites while a profile save is pending. A PUT quota in feedback is
labelled as the snapshot reported by that save; list quota comes from its latest
GET. Old-account notices/quota cannot populate another identity's UI.

## Verification and next slice

Synthetic unit/component and intercepted Chromium desktop/mobile checks cover
query-free CSRF writes, fresh identity checks, changed/unavailable accounts,
idempotence at quota, server rejection, typed deletion, delayed/time-out replies,
readback without replay, incomplete/read-failed snapshots, CSRF recovery, auth
serialization, app disposal, row/view unmount, last-page/empty transitions and safe
feedback. No application database, real account, email, loader or NHL call is used.
Existing isolated backend tests remain evidence for actual persistence, ownership
and quota concurrency.

Next implement the private aggregated Favorites gamelog using the existing scoped
API and this private read boundary. Comparison and private notes/positions follow;
account/preferences, search, visual design and production cutover remain later work.
