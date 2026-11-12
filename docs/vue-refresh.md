# Vue saved-data refresh and freshness

The scoreboard and game-detail routes now share **Auto-refresh**, **Refresh now**
and last-check feedback. These controls read the existing public JSON APIs only;
they never call NHL services, start loaders or make writes. Celery/loader updates
must still run separately. Existing Django refresh endpoints and deployment routes
remain unchanged.

## Check policy

- After a successful initial load, check every **60 seconds**, measured from the
  previous check's completion. There is at most one check per view at a time.
- Auto-refresh starts enabled for each mounted view. Unchecking it stops future
  automatic checks; a read already in flight may finish. Manual refresh still works
  while paused, provided the view is ready, visible and online.
- Hidden and offline tabs stop scheduling checks. Becoming visible/online checks
  again when ready and automatic refresh is enabled. No overlap is created if a
  check is already running. Pausing automatic checks also suppresses resume checks.
- Failed checks retain the last accepted data. Delays increase from the normal
  minute to **two minutes, four minutes, then a five-minute cap**. Success resets
  the normal cadence. There is no replay of writes or infinite tight retry loop.
- Saved API read batches have a **10-second timeout**. Initial failures remain the
  existing retryable loading/error states; background failures show an unchanged-
  data notice with manual retry and bounded-delay automatic retry when enabled.
- Navigation clears obsolete results, cancels reads and resets the retry state for
  the new resource. Old responses cannot overwrite the current view, its check
  status or a newer pending request. Unmount removes timers/listeners and aborts
  the active read. Views do not poll missing/invalid initial game IDs.

The scoreboard keeps its exact selected date/page, even when the API suggests a
new latest date. An initially empty date store pins its API-provided Pacific
reference date for later checks rather than following a future fallback. A date
being edited in the form is not overwritten by a background check. Date discovery
and scoreboard results are accepted together, so failure of either read preserves
the previous batch. Game-detail checks send no browser return-context parameters
to the query-free game API.

## Save time, check time and state observation

**Saved record update** remains the API's successful database-publication time.
**Last checked** uses `freshness.checked_at` from the last accepted game-data
response. A successful check need not change the saved record; a failed check
advances neither displayed time. Empty initial date discovery has no game-data
check timestamp, so the UI does not invent one.

The out-of-date warning uses the server's `age_seconds` plus monotonic browser
elapsed time since receipt, updating approximately every **15 seconds** while the
view is visible/ready, even with automatic network checks paused. This avoids
assuming that the browser's wall clock matches the server. The API's stale flag
also remains evidence. Missing ages stay unknown; empty results and old final
records do not become stale merely because of age. The API's freshness final flag
controls that rule, independently of the shared legacy state label.

Storage age and check success never establish current NHL state or an observation
time. Saved live/final/unknown/conflict labels retain the
[existing evidence contract](game-state-api.md), including null observation times.
Partial/unavailable fields remain explicit and do not become zero after refresh.

Background checks keep the ready branch mounted. Stable game/player keys preserve
unchanged controls, roster regions, table scroll and keyboard focus. Refresh buttons
use guarded `aria-disabled` state while checking, allowing the focused control to
remain in place. User navigation still has its ordinary loading/focus behavior.

## Verification and next phase

`make frontend-test` uses fake timers for cadence, backoff cap/reset, overlap,
visibility/connectivity, freshness aging, deadlines and disposal. View regressions
check immutable selection/drafts, last-good retention, timeouts and navigation races.
`make frontend-test-browser` uses Playwright's controlled clock plus intercepted API
responses at desktop/mobile sizes, including table/input focus, horizontal scroll,
pause/manual recovery, hidden/offline resume and exact URL preservation.
No real application database or NHL requests are used.

No backend/schema, dependencies, migrations or Python coverage scope change is
required. The frontend scoreboard/game pilot is complete for this phase. Continue
with the recorded session/CSRF and login/logout UI phase before registration,
recovery and season/player tables. Private mutations and any later refresh of
user-owned data need explicit cancellation/invalidation semantics; this public
polling code does not introduce private flags or automatic mutation retries.
