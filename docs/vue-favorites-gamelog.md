# Vue aggregated Favorites gamelog

`/favorites/gamelog` uses the existing private
[aggregated Favorites API](favorites-gamelog-api.md). The Favorites list provides
**All saved Favorite games** and, when a season is known, **Selected-season Favorites
game log** links. A direct visit defaults to skaters and all saved seasons/dates.
No calendar/latest-SBS default is borrowed from the list or public profile.

Entry links pass the selected typed group and optionally its season. Other list
filters, mode and page are preserved only as return context, not silently applied
to game rows. The aggregate population is the account's Favorites in that typed
group, including saved players outside the filtered list page. Gamelogs have no
averages mode; their TOI and counting fields describe actual saved games.

Normal development uses Django's configured database through the API; run Django
and Vite separately using the [frontend instructions](../frontend/README.md).
Automated fixtures are not demonstration data for the running site. Existing
Django pages, API contracts and production routing remain unchanged.

## Rows, identity and saved evidence

Each row has explicit current player name, skater/goalie type and NHL ID. Profile
position is displayed separately from game position/number. Missing game values
never fall back to profile metadata. A blank name has an NHL-ID display fallback,
without changing the API's underlying identity/name ordering.

Counts mean player-game **rows**, not distinct games or saved players. Two favorites
in one game stay separate, and identities are not deduplicated by date/game ID.
The view displays API count/pages without a 200-row cap or fetching all history.
Quota describes both unfiltered membership groups, independently of row count,
filters or pagination. A favorite without any game rows remains in the ordinary
list/quota. Empty row selections do not imply an empty saved list.

Actual `toi_seconds`, `pp_toi_seconds` and `sh_toi_seconds` format as `mm:ss`; known
zero stays `0`/`00:00`, unknown stays `—`. Goalie fractions display as percentages,
with decision and goalie-only fields kept separate. No season/career average or
client-side arithmetic supplies game statistics.

Unlinked/orphan rows retain their explicit unknown statistics/sides/opponents and
never invent game links from a date. Undated linked games retain links and missing
row data. Game-state labels preserve unknown/conflict evidence independently of
player availability; score or row completeness never supplies a live/final state.
Dates display their saved ISO year/month/day, without guessing seasons or shifting
them into the browser's timezone. Explicit season filtering remains the API's
verified regular-season game-ID rule, excluding unknown-provenance orphan dates.

## Filters and navigation

Controls expose typed group, optional season, literal favorite-name search,
schedule-date bounds, exact comma-separated teams/opponents, numeric bounds/
missing-value filters, ordering and page size. TOI filters use seconds; save
percentage filters use fractions (0–1). No ranges/facets are guessed from a page.
Type changes reset incompatible numeric filters and ordering.

Identity keys `player_name`, `player_last_name` and `player_nhl_id` are combined
with existing game/statistic ordering fields, e.g. `player_name,-date`. Sorting
and filtering occur globally in Django before pagination; the frontend preserves
response order. These keys/search do not broaden the public individual gamelog
contract. Blank/repeated/type-inappropriate selectors, unsupported fields/mode/
owner parameters and malformed dates/ranges fail before private GETs.

Apply/sort resets pagination, while page changes/reload/back preserve the applied
URL. An explicit empty season stays selected. **Clear filters** returns to all
saved seasons while retaining the typed group and source-list destination.
**Refresh gamelog** performs a saved-data read; polling or freshness claims are
not introduced. Unsaved form drafts are not persisted. Wide tables remain in a
labelled keyboard-focusable mobile scroll region.

The validated source Favorites URL is the back destination. Without a valid source,
the back link selects the current typed Favorites group and any explicit season.
Game links use `favoriteLog` context; profile links use `returnTo`. Both public
screens validate that local private route before offering **Back to Favorites
gamelog**, preserving name/order/filter/page and nested list context through reload.
Invalid context retains the existing public fallback. Returning after logout
re-enters the private session gate. Existing route/URL-length limits apply.

## Private read boundaries

The view reuses `usePrivateRead`: unknown/busy/anonymous/unavailable sessions issue
no private GET. The authenticated session client reads only the scoped endpoint;
there are no per-row profile/game requests until navigation. Auth/revision/query/
unmount changes clear names, rows and quota and abort pending reads. Late old-account
or old-query results cannot overwrite a newer selection. There is no application
packet cache or browser storage of game rows.

A 403 prompts explicit session checking without automatic read/check loops. Failed
sessions, timeouts and page/protocol errors clear prior private rows and provide
safe messages/request references plus retry/first-page/filter recovery. The shared
ten-second read deadline applies. Backend authentication/owner locking and existing
private/no-store responses remain authoritative; no new cross-tab identity protocol
is introduced.

Return context is never forwarded to APIs. Requests contain only validated scoped
filters/type/page. API pagination/resource URLs are not followed; local routes use
pagination availability flags. No membership write, loader, email or NHL request is
triggered by this view.

## Verification and next slice

Synthetic unit/component and intercepted desktop/mobile Chromium checks cover
same-game multiple players, null/zero and orphan/undated rows, actual PP/SH TOI,
identity ordering/search/filter/page requests, all/empty seasons, missing-log quota,
private game/profile/list round trips, sign-in/expiry, logout/account switches,
unavailable sessions, delayed responses and deadlines. Public individual-gamelog
validation remains unchanged. Tests do not use application DB, real accounts,
email, loaders or NHL calls.

Next implement the private comparison UI using the existing season/career API and
private identity/revision boundaries. Comparison mutations, private notes/positions,
account/preferences/search, visual design and production cutover remain following
focused slices.
