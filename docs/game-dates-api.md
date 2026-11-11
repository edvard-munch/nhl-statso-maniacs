# Saved game-date discovery and navigation

`GET /api/v1/games/dates/` discovers stored Pacific NHL schedule dates. It reads
`Gameday.day`, including saved days with no linked games; it does not certify that
all games or player statistics have loaded. Multiple games on one date do not
produce duplicate dates, and undated games do not establish dates. No loader calls,
NHL requests, writes or HTML rendering occur. The existing scoreboard remains an
exact-date resource and never silently substitutes this endpoint's selection.

## Request and response

Optional `date` must be an actual calendar date, exactly `YYYY-MM-DD`. It is a
navigation reference, not a list filter. Omission uses today's date in
`America/Los_Angeles`, independently of the viewer's timezone and the Django
application timezone, including Pacific daylight-saving transitions.

`page` defaults to 1; `page_size` defaults to 50 and is capped at 100. Positive
integer strings are required. Unknown, repeated, blank or invalid query values
return JSON 400. Empty page 1 is valid; out-of-range later pages return JSON 404.
The normal `count`, `next`, `previous`, `results`, `meta` response shape applies.
Each result is `{date: "YYYY-MM-DD"}`. Results contain all saved dates, newest
first, with database pagination; the navigation reference does not reorder or
filter them. Pagination links preserve supplied query parameters.

`meta` is independent of the current result page:

- `requested_date`: supplied `date`, or null when omitted.
- `reference_date`: supplied date or today's Pacific date.
- `schedule_timezone`: `America/Los_Angeles`.
- `latest_date`: newest saved gameday, or null for an empty store. This may be a
  future saved date; the API does not infer that it has been played.
- `selected_date`: the reference when it exists in saved dates; otherwise the
  latest saved gameday. An empty store has null selection.
- `used_fallback`: true only when a nonnull selection differs from the reference.
- `previous_date` / `next_date`: nearest earlier/later saved dates relative to the
  selection, skipping gaps. Missing neighbors are null.
- `window`: up to six saved dates in chronological order around the selection.
  Normally three dates precede it and two follow it. At either edge, the window
  shifts to retain six dates when available. It never invents dates to fill gaps.
  Empty stores return `[]`.

For example, a request referencing an unsaved date returns that original date in
`reference_date`, the latest saved date in `selected_date`, and
`used_fallback: true`. A client can explicitly request
`/api/v1/games/?date=<selected_date>` to adopt that fallback. Requesting the original
unsaved date from the scoreboard still returns an empty collection.

## Read and query limits

Anonymous and signed-in viewers receive the same public data; responses use
no-store headers. GET/HEAD are reads and unsupported writes return JSON 405.
A nonempty request uses six SELECTs: paginated count/results, latest date,
reference existence, selection rank and the bounded window. Only the requested
page and six window dates are materialized, regardless of the history size. An
empty store uses one COUNT. The unique `Gameday.day` index supports date lookups;
no migration or new index is introduced. Neighbor metadata and window describe
saved dates, not live/final state or freshness evidence.
