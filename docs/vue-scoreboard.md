# Vue saved scoreboard

The frontend route `/games` browses stored games through the generated
`gameDatesList` and `scoreboardList` operations. It does not start ingestion or
contact NHL services. Run Django and `make frontend-dev` as described in the
[frontend workflow](../frontend/README.md), then open
http://127.0.0.1:5173/games. Existing Django pages and deployment routes are unchanged.

## Date selection and navigation

- With no `date` query parameter, ask the date-discovery API for its Pacific/default
  selection, then replace the URL with that exact saved date. A latest-date fallback
  is disclosed; it may be a future saved date, not the latest played game.
- With an explicit `date=YYYY-MM-DD`, keep that date even when discovery recommends
  another. An unsaved date can correctly show no saved games. Never fall back based
  on the viewer's local clock or silently replace a deliberate empty-date request.
- The form, bounded saved-date window and previous/next saved-date controls update
  the URL. Neighbors are used only when navigation metadata describes the displayed
  date, so fallback metadata cannot produce misleading previous/next actions.
- Query `page` selects a result page for that date. Pagination preserves the date;
  selecting another date resets to page one. Reload and browser back/forward restore
  the query state. Unavailable pages offer a first-page action.
- Empty date stores remain empty, using the API's reference date for the form.
  Invalid/duplicate date and invalid page values are rejected before requests.
  Schedule dates are formatted as calendar labels without shifting across timezones.

Date discovery uses its bounded window/neighbor metadata rather than downloading
all historical dates. Scoreboard pagination uses the API's count/next/previous
signals and the explicit 50-game page size. Query values are passed as generated
SDK options, not copied blindly from the browser URL.

## Saved-data presentation

Cards show saved away/home team names and scores. Genuine zero remains zero;
missing/ambiguous teams and scores remain unavailable. Labels use the explicit
`state` evidence, including conflict, rather than deriving live/final status from
`is_final`, a score or storage freshness. OT/SO outcomes remain explicit.

“Saved as live” is not a current NHL observation. The view explains the saved-state
limit and separately shows storage update time, staleness and partial-data notices.
It does not manufacture clocks, periods, start times or observation timestamps.
See the [scoreboard](scoreboard-api.md), [date-navigation](game-dates-api.md) and
[state-evidence](game-state-api.md) contracts.

Loading clears old results immediately. Date/page changes and unmounting abort
obsolete requests; aborted/late replies cannot overwrite the current selection or
its error state. Failures have a retry action, JSON error correlation references
where available, and generic messages for non-JSON proxy failures. Submitting the
unchanged date form explicitly reloads it. There is no timer or automatic refresh.

## Verification and next slice

`make frontend-test` covers typed synthetic data, default/exact/empty selection,
invalid inputs, missing/zero values, live/final/conflict evidence, failed reads,
pagination, cancellation and delayed replies. Chromium checks in
`make frontend-test-browser` exercise generated-client Fetch requests with mocked
API responses at desktop/mobile sizes, including back/reload, Pacific date labels,
empty/error recovery and pagination. They use no application database or live NHL
requests. Existing frontend CI includes both suites and the production build.

Next add the game-detail view and card navigation using the existing typed API.
Automatic refresh/freshness interactions and production route cutover remain
separate changes. No backend/schema, dependency or coverage-scope change is needed
for this scoreboard slice.
