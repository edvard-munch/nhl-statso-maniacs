# Vue teams and season contributions

Open `/teams` from home or the main navigation. Team names link to `/teams/{nhl_id}`,
which shows saved metadata and a separately paginated season contribution table.
The generated [team APIs](teams-api.md) supply all data; the frontend never runs
loaders, queries the database directly or computes team splits from overall totals.
Existing Django pages and production routing remain unchanged.

Run Django and Vite in separate terminals using the
[frontend instructions](../frontend/README.md). Normal development uses Django's
configured database through the API; synthetic fixtures are used only by tests.
If Django is stopped, the frontend shows a load error rather than demonstration data.

## Saved team directory

The directory includes all saved identities, including historical teams and teams
without player statistics. Names, conference/division and arena are current saved
metadata, not an assertion of active status or a historical metadata reconstruction.
Missing saved strings display as `—`.

Search matches name/abbreviation through the backend. Conference/division inputs
accept exact comma-separated saved names. Named ordering supports multiple fields
and `-` descending; page size/pagination, reload and back/forward preserve the URL.
Applying filters resets the page. There is no directory facet endpoint, so choices
are not inferred from one page. An empty first page remains a normal empty result.
Errors clear previous rows and offer retry, clear filters and first-page recovery.

## Team detail and exact season splits

An omitted season resolves the global latest loaded season through the team API,
then pins that ID in the URL. It does not choose the calendar or a team's last
populated season. Valid explicit empty seasons remain selected. A team with no
loaded season or no contributions keeps its metadata visible.

Only the exact team's selected-season contributions with positive known GP are
returned. Combined-only totals, another team's split, overall season aggregates
and current roster foreign keys never fill a missing row. For example, six BUF
games/three goals remain six/three on BUF; a profile can separately show ten overall
games/four goals. Skater averages and goalie rates come from the scoped API values,
not frontend arithmetic. Missing fields remain `—`, known zeros remain zero, and
partial rows are labelled. TOI is per game (`mm:ss`); goalie save fractions display
as percentages. No player refresh timestamp is invented.

The selected group supports skater totals/averages and goalie totals/rates. Changing
player type clears incompatible filters/order. Position and jersey number are
current biography, not historical reconstruction. Name search, current positions/
nations, rookie and birth-date selection, all numeric bounds/missing-value filters,
ordering and page size use the shared catalogue query contract except `team` is
rejected: the path selects the team. TOI bounds use seconds, save-percentage bounds
use fractions (0–1). Known zero and false selections are preserved.

Filtering/sorting occurs on the backend before pagination. There is no scoped
filter metadata endpoint; global Players facets/ranges and single-page guesses
are not used. Inputs use exact codes with comma-separated OR choices. Applied
selection, ordering and paging survive reload/back; applying or sorting resets
the page. Unsaved drafts are not persisted. Wide tables remain in labelled,
keyboard-focusable mobile scroll regions.

## Links, request boundaries and recovery

Team links retain the validated directory URL. Player links carry typed identity,
season/mode and the full applied team URL. Profiles offer **Back to team** for valid
team context while preserving the existing **Back to players** catalogue behavior.
Changing profile selections preserves that source context. Team routes also work
as public sign-in return destinations. Existing URL length limits apply.

Browser return context is never forwarded to APIs. Team metadata receives only
season; contributions receive validated selection/page filters. API-provided
resource/next/previous URLs are not followed; local routes use pagination flags.
Saved websites are explicit external links only for HTTP(S) URLs without embedded
credentials; other saved strings remain plain text. Destinations are not fetched
or verified by tests or during rendering.

Reads share the ten-second saved-read deadline, abort on navigation/unmount and
ignore late responses. Old detail/rows clear for a new selection. Contribution-page
failures keep confirmed team metadata visible and offer retry/first-page recovery.
Missing team identities and malformed selectors are explicit, with no lookup or
season fallback guesses. Safe messages/request references replace upstream bodies.
No team polling or new freshness claims are introduced.

## Verification and next slice

Synthetic unit/component and intercepted desktop/mobile Chromium checks cover
saved/historical metadata, exact traded-player values versus overall profiles,
skater averages/goalie rates, zero/null, empty stores/seasons, context round trips,
filter/order/pagination URLs, errors, stale responses and request deadlines. No
application database, real account, email, loader or NHL service is used. The
existing isolated backend suite remains the evidence for split selection rules.

[Private Favorites reads](vue-favorites.md) now implement session-aware loading and
account/revision invalidation. Membership actions follow, then comparison and private
player fields. Account preferences, search, saved-video presentation, visual design and production cutover remain
separate work.
