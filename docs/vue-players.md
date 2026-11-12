# Vue Players catalogue

Open `/players` in the Vite frontend, or use **Players** in the main navigation.
The view uses the generated public `/api/v1/seasons/`, `/api/v1/players/` and
`/api/v1/players/filters/` clients. Existing Django tables and production routing
remain unchanged. Start Django and Vite as described in the
[frontend instructions](../frontend/README.md).

## Season and statistics selection

An omitted season is pinned in the URL to the API's default loaded season, not
the calendar year. All season metadata pages are read; supplied pagination URLs
are never followed. An explicitly selected empty season stays selected, and an
empty loaded store does not invent a season or substitute snapshot statistics.

Skaters support totals and per-game averages. Goalies support totals with rates;
switching player type resets incompatible filters and ordering. GP remains games
played, skater TOI remains per-game time formatted as `mm:ss`, and goalie save
fractions are displayed as percentages. Numeric save-percentage filters still use
fractions (0–1), and TOI filters use seconds. Unknown values remain `—`; genuine
zeros remain zero. Partial rows are labelled. Teams show season participation,
while displayed statistics describe the whole season, including traded players.
Biography filters use current profile values.

The catalogue includes positive known GP players under the existing API rules.
It does not establish the population of a private Favorites/comparison list. No
reliable player refresh timestamp exists; the view makes no freshness claim and
does not poll loaders or the NHL API.

## Filters, ordering and URL state

Choose season/type/mode, search, rookie status and page size, then **Apply selections**.
Expand **Filters and ranges** for season teams, positions, nations, birth-date bounds
and every supported numeric minimum/maximum/missing-value filter. Ranges come from
the unfiltered season/type/mode metadata. Categorical options cover the unpaginated
population after non-categorical filters; all categorical selections are excluded
from option generation together. Selected codes remain removable even if absent
from the latest options. Options are refreshed on apply, not every keystroke.

The Ordering field accepts named comma-separated API fields, with `-` for descending;
its suggestions list supported fields. Table statistic buttons toggle that field's
ordering. Filtering/sorting is done on the backend before pagination. Applying
selections, clearing filters and sorting reset the page. Pagination preserves the
applied query and uses locally constructed routes, not API-provided next URLs.
Reload and browser back/forward restore the applied controls. Public sign-in return
navigation also accepts this route. Unsaved draft edits are not persisted.

Malformed/repeated/unknown query parameters are rejected without silently dropping
filters. Errors clear prior results and offer explicit retry/clear/first-page actions.
Requests have the shared ten-second saved-read deadline and abort on navigation or
unmount; late responses cannot overwrite a newer selection. Catalogue and filter
metadata must both succeed before results are shown. Wide tables scroll inside a
labelled keyboard-focusable region without widening the mobile page.

## Verification and remaining work

Component/unit tests cover numeric zero, missing values, pagination independent
metadata, defaults, empty stores/seasons, type switching, URL state, stale responses,
error recovery and deadlines. Chromium checks exercise the workflow at desktop and
mobile sizes with intercepted APIs and synthetic records. No application database,
real accounts, email, loaders or upstream NHL services are involved.

Catalogue rows now link to [typed profiles and season history](vue-player-profiles.md),
preserving the applied catalogue context. [Verified saved gamelogs](vue-player-gamelogs.md)
now preserve that context through game links. [Team screens](vue-teams.md), including exact team-season splits, are also implemented.
Account preferences
(including measurement presentation), private resources, visual design and production
route cutover remain later focused slices. Private membership actions remain deferred
until their frontend workflows exist.
