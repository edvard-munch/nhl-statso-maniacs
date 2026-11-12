# Vue saved player gamelogs

Open `/players/{player_type}/{nhl_id}/gamelog` directly, or use the profile's
**View selected-season game log** / **View all saved games** links. Identity remains
explicitly skater/goalie plus NHL ID, including overlapping IDs across models.
The generated [gamelog API](player-profile-api.md#verified-saved-gamelog) supplies
verified saved row statistics; the profile API supplies the current saved name
for the heading. Neither request runs a loader or calls NHL services.

## Scope and filters

Omitted `season_id` means **all saved seasons and dates**, independently of the
profile API's default season. Nothing pins a direct gamelog visit to the calendar
or latest season. The selected-season profile link passes its resolved season
explicitly; the all-saved link omits it. An explicit empty season stays selected.
Clearing filters removes season/date/team/statistic selections and returns to the
all-saved scope, preserving the profile return destination.

Season ID, inclusive schedule-date bounds, comma-separated saved teams/opponents,
named ordering and page size are available in the form. **Statistic filters**
provides every type-appropriate numeric minimum/maximum/missing-value control.
Goalie decision is display/order data, not a numeric bound. Numeric zeros and false
missing-value selections are retained. Repeated, unknown, empty, reversed or invalid
URL filters are rejected without silently broadening the request.

Ordering supports comma-separated API fields and `-` for descending; statistic/date
buttons toggle primary ordering. Filters and sorting run on the backend before
pagination. Applying or sorting resets the page; pagination, reload and back/forward
preserve the applied query. Unsaved form drafts are not persisted. There is no
public gamelog facet/range endpoint, so no ranges are guessed from a page or borrowed
from season catalogue metadata.

## Saved evidence and units

The table uses actual game `toi_seconds`, `pp_toi_seconds` and `sh_toi_seconds`,
formatted as `mm:ss`. Season/career averages never supply these values. A known
zero is `0` or `00:00`; missing values stay `—`. Goalie save fractions become display
percentages while filter bounds remain fractions (0–1); duration bounds use seconds.

Player-row availability is independent of saved game state. Unknown statistics,
teams and opponents remain unknown; orphan rows gain no inferred metadata. A date alone never creates a game
link or historical team assignment. Known linked games remain linked even with an
undated/missing player row. Saved state labels retain unknown/conflict semantics;
no state is inferred from scores, player availability or profile freshness.
The table is horizontally scrollable inside a labelled keyboard-focusable region
without widening the mobile viewport.

## Context and failures

The gamelog's `returnTo` accepts only the same typed player's valid local profile,
including its season/mode/history page and nested catalogue context. Unsafe or
unrelated destinations fall back to that typed profile. Game links carry the full
applied gamelog in `gamelog`; game details validate that local route before offering
**Back to player gamelog**. Reloading the game preserves the return chain. Absent or
invalid gamelog context retains the existing scoreboard return behavior. Gamelogs
also work as public sign-in return destinations. Existing return-length limits apply.

Navigation context never enters API queries. The profile name read receives only
an explicit season when present; the gamelog receives its validated filters. The
profile's default season does not change gamelog scope. API-provided resource and
pagination URLs are never followed; local routes use pagination availability flags.

Reads have the shared ten-second deadline and abort on navigation/unmount. Both
name and log reads must succeed before rows display. Errors clear previous name/
rows and offer explicit retry, first-page and clear-filter recovery. Late responses
cannot replace a newer typed identity or selection. Safe messages and request IDs
replace upstream error bodies. Gamelog polling is not introduced; existing game-page
saved-data refresh continues unchanged.

## Checks and next work

Unit/component and intercepted desktop/mobile Chromium checks cover actual PP/SH
TOI, known zero versus unknown, goalie fields, all-saved/empty-season scope, filtering,
URL/history pagination, contextual game/profile/catalogue round trips, missing pages,
errors, stale responses and deadlines. Tests use synthetic records without application
DB, real accounts, email, loaders or NHL calls. Backend verification remains the
existing isolated API regression suite's responsibility.

Next add public team browsing and team-season contribution screens. Private lists,
account preferences, saved-video presentation, visual design and production routing
remain later focused work.
