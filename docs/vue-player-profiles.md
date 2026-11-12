# Vue player profiles and season history

Catalogue player names now link to `/players/{player_type}/{nhl_id}`. Identity is
explicitly `skater` or `goalie` plus NHL ID; position never selects the model and
failed lookups do not fall through to the other type. Direct links also work for
saved players without positive GP or selected-season statistics.

The view uses the generated profile and season-history APIs documented in the
[profile contract](player-profile-api.md). It reads saved data only, with no loader,
NHL request, private membership lookup or write. Existing Django pages and production
routing remain unchanged. Run Django and Vite using the
[frontend instructions](../frontend/README.md).

## Biography, selected season and career packets

Biography, current team, photo, position/number and draft data describe the current
saved profile. Height/weight show the saved cm/kg/lb values with explicit units;
account measurement preferences remain a later frontend slice. Current team does
not establish historical team participation. No player freshness time is invented.

The selected season is separate from career totals and saved career averages.
Skaters show both career packets even when the selected mode is totals or averages;
goalies show their career totals/rates without an averages control. Career values
are never summed from displayed history or recalculated from incomplete packets.

The season-ID input accepts consecutive eight-digit years. Clearing it resolves
the latest loaded season through the profile API and pins that ID into the URL;
an empty global store keeps no season. Explicit empty/unloaded seasons stay selected.
History-page buttons can also select any season displayed on that page. Skaters
support totals/per-game mode; goalie averages are rejected before API access.

Missing, unverified and partial packets remain labelled, with individual unknown
values shown as `—` and genuine zeros retained. Nullable GP is never turned into
zero. Skater TOI remains per-game `mm:ss`, including in total packets. Goalie save
fractions display as percentages; GAA remains the API's per-60-minute rate.

## History and navigation

History is paginated at 25 seasons per page. Each overall season row is separate
from its exact team contributions, including unknown team abbreviations. An
unverified contribution stays unknown even when overall statistics are available.
History follows the selected mode but is not filtered to the selected season.

`season_id`, `mode` and `history_page` preserve the applied selection through reload
and browser navigation. Applying a season/mode form resets history pagination;
selecting a season from the current history page retains that page. Catalogue links
carry the full applied catalogue URL in `returnTo`. Only a validated local Players
catalogue is accepted as that destination; unsafe/unsupported values fall back to
`/players`. Profile routes also work as public sign-in return destinations.

Browser context is never forwarded to APIs: the profile receives only season/mode,
while history receives mode/page/page size. Server-provided history/gamelog/next URLs
are not followed. Pagination uses locally constructed routes and next/previous
availability flags. Unknown/repeated/invalid selection parameters fail explicitly.

Requests abort on navigation/unmount and share a ten-second read deadline. Old
identity/statistics clear on a new selection; late results cannot replace a newer
player. Profile failures have retry/default-selection actions, while history-page
failures leave confirmed biography/career packets visible and offer retry/first-page
recovery. Errors show safe messages and request references, not upstream response
bodies. Wide statistics tables stay within keyboard-focusable mobile scroll regions.

## Verification and next slice

Synthetic unit/component and intercepted desktop/mobile Chromium tests cover typed
identity, zero/null values, independent career packets, unknown splits, empty seasons/
history, URL round trips, safe returns, missing pages, stale responses and deadlines.
No application database, real account, email or NHL service is used. Backend packet
semantics remain covered by the existing isolated backend regression suite.

Next add the verified saved gamelog frontend and game-detail navigation with preserved
profile/catalogue context. No inactive gamelog link is shown by this slice. Team
screens, saved-video presentation, private actions, measurement preferences, visual
design and production cutover remain separate work.
