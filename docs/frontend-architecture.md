# Frontend architecture and migration plan

Recorded: 2026-11-09. This records the target architecture; frontend/resource
migration remains pending. The [API foundation](api-conventions.md#implemented-api-foundation)
is now implemented. Architecture/API conventions themselves are one documentation-only commit. Budget
roughly **25–30 focused commits for the full migration**, including this one;
that is an estimate, not a promise to combine unrelated changes to meet a count.

## Goal and working proposal

Move all public application pages and interactions to a Vue frontend. Django
provides JSON data, authentication, validation and business rules; PostgreSQL and
Celery continue their existing persistence/loading roles. A frontend request must
never trigger NHL ingestion. Preserve the tested season, ownership and quota
contracts throughout the transition.

Decision confirmed: **Vue 3, Vite and TypeScript**, running as a browser-rendered
application. Nuxt/server rendering is outside the current implementation plan.
Django supplies JSON; the production frontend is a static build. Public indexing
and per-page social previews remain a known limitation to review if required later.

**Functionality comes first; mobile usability is required from the first slice.**
Preserve working statistics, navigation and account workflows before visual polish.
Use responsive layouts, usable touch controls and accessible labels/focus states.
Dense statistics tables may scroll within their own container on narrow screens;
controls and navigation must fit without page-wide horizontal overflow. Verify
key workflows at desktop and mobile viewport sizes as each slice is introduced.
A visual redesign, final theme and extensive visual snapshots can follow later.

## Current API scope and next slice

The API foundation/schema, saved scoreboard, game-detail, loaded seasons and
Players catalogue, team metadata/contributions and public profiles/history/gamelogs
are implemented. JSON CSRF/session discovery and login/logout are also implemented.
Registration, password recovery and the private [Favorites list/membership API](favorites-api.md)
and [comparison API](comparison-api.md), plus the
[aggregated Favorites gamelog](favorites-gamelog-api.md), are implemented.
[Private notes and position overrides](private-player-data-api.md) are implemented.
[Account settings](account-api.md) and the [profile image API](account-image-api.md)
and [search/autocomplete](search-api.md) are implemented. Review workflow coverage
and outstanding provenance decisions before introducing the Vue/Vite scaffold.
The [2026-11-11 completeness review](api-completeness-review.md) found four
remaining parity contracts. Players filter metadata is now implemented via
`/api/v1/players/filters/`, and [saved game-date navigation](game-dates-api.md)
is implemented at `/api/v1/games/dates/`. Shared [saved game-state evidence](game-state-api.md)
is also implemented, together with [Favorites gamelog player-identity ordering](favorites-gamelog-api.md#player-identity-ordering).
The G1–G4 API parity slices are complete; the next checkpoint is remaining
pre-cutover decisions and client tooling. The [reviewed offline schema](openapi-workflow.md)
and generated TypeScript SDK are checked into Git and checked for drift in CI.
The [Vue/Vite scaffold](../frontend/README.md) now provides the responsive shell
and development proxy; scoreboard/game workflow migration is next.
Projection/admin decisions and auth deployment hardening precede their affected
cutovers. Existing API families being present does not yet establish full UI parity.
Legacy HTML/AJAX endpoints stay available until their tested replacements cut over.

The implementation order is **API first, frontend second**. Complete and test
seasons/players, teams, profiles/gamelogs, authentication, saved lists/private
fields, account settings/uploads and search before scaffolding Vue/Vite and its
generated client. Small API adjustments may still follow frontend integration.
Existing pages remain usable until their tested replacements are ready.

## Boundaries

| Responsibility | Owner |
| --- | --- |
| Pages, layouts, navigation, links, labels, numeric/time formatting, responsive tables | Frontend |
| Public titles, descriptions, canonical URLs and share metadata | Frontend |
| Season selection/projection, team contributions, averages and missing-value semantics | Django services/readers |
| Input validation, permissions, private ownership and concurrent quota enforcement | Django |
| Server filtering/sorting/pagination and explicit JSON serialization | Django API |
| Ingestion, retries, overlap locks, cooldowns and scheduled updates | Existing commands/Celery |
| Saved data and durable scheduling/run history | PostgreSQL |

Reuse `season_stats`, the loader contracts and `saved_actions.locked_user`.
Extract presentation-neutral projections from modules such as `player_table`,
which currently mix data with HTML. Client validation improves the interface;
backend validation and permissions remain authoritative. Do not move statistics
formulas or quota checks into components.

## Repository, tools and hosting

Keep one Git repository with a `frontend/` application, its own package manifest
and lockfile, and the existing uv-managed backend. The scaffold pins compatible
Vue/Vite tooling independently of Python dependencies.

The selected frontend uses Vue/Vite/TypeScript, Vue Router, pnpm, ESLint/Prettier,
Vitest and Playwright. Evaluate Vue Query where shared browser caching/mutations justify it;
do not create two competing sources of cached page data. Pinia is optional if
substantial client-only shared state emerges. TanStack Table is the proposed
statistics-table engine; Tailwind/shared accessible components remain proposed
for page work. The scaffold uses a small responsive base stylesheet.
Storybook/visual snapshots can follow once reusable components exist.

Django REST Framework supplies the API, drf-spectacular its OpenAPI schema, and a
pinned Kubb generator supplies TypeScript types/named client functions through
an app-owned Fetch transport. Query hooks remain deferred until workflow needs
justify a caching library.
Generated code must be reproducible from a checked schema without a live NHL
connection or application database.

Use one public origin: route `/api/v1/` to Django, frontend routes to the frontend
build/runtime, and media to the configured storage/web server. Development uses a
proxy to preserve cookie/CSRF behavior. Separate repositories, cross-origin browser
authentication and independent breaking release cycles are not needed initially.
Serve Vite's production build with frontend-route fallback, keeping `/api/v1/`
and media routing separate. Do not deploy the Vite development server.

## Authentication and cache ownership

Retain Django session authentication and existing accounts. JSON CSRF/session
bootstrap, login/logout, registration and password recovery are implemented;
account settings GET/PATCH and dedicated image uploads are implemented. Enforce CSRF on login as well as authenticated unsafe requests. The session cookie remains
HTTP-only, with deployment security attributes configured for the public origin.
Do not introduce JWT/local-storage tokens simply because the UI is separate.

Public statistics responses contain public data only. Load favorite/comparison flags
and notes through private endpoints. Personal responses are private/no-store;
public responses must not contain another account's state. Do not forward a
visitor's cookies into a shared public cache. Clear private frontend state on
logout or account changes, cancel superseded requests, and prevent older reads
from restoring pre-mutation selections. Preserve the existing user-row quota lock.

Frontend API reads use saved statistics. Preserve current freshness semantics:
save time differs from check time, missing fields differ from zero, and successful
polling does not establish NHL source freshness. Retry public reads with bounds;
mutation retry semantics must be explicitly defined and tested.

## Migration sequence and commit budget

Each range is an estimate for small, reviewable commits, not a single broad patch.
The current queue completes the remaining JSON API families with regression and
OpenAPI tests first, then introduces frontend scaffolding, generated-client checks
and the scoreboard/game UI pilot. The phase estimates below group API/UI scope;
they do not require implementing the two halves in the same commit.

| Phase | Estimated commits | Acceptance evidence |
| --- | --- | --- |
| Architecture and API conventions | 1 | Reviewable decisions, open questions and migration contract |
| API foundation, JSON errors, schema/client generation, frontend scaffold/CI | 3–4 | Schema validation, type/lint/unit checks, production build |
| Scoreboard/game JSON APIs and frontend pilot | 4 | Date/roster/statistics contracts, responsive browser rendering, polling/failure recovery |
| Session auth, registration and password recovery API/UI | 4 | CSRF, identity, expiry, validation and browser workflows |
| Players API and frontend tables | 2–3 | Season/filter/sort/pagination parity and URL state |
| Teams, public player profiles and gamelogs API/UI | 4 | Team splits, historical values, canonical URLs and metadata |
| Favorites/comparison and private notes/positions API/UI | 3–4 | Ownership, idempotence, quota concurrency and recovery |
| Account/profile settings, uploads and search | 2–3 | Existing forms/measurements/search behavior and privacy |
| Route cutover, legacy retirement and deployment documentation | 2–3 | Browser parity, production routing/build and verified removal inventory |

This totals 25–30 commits. Any replacement for Django admin, additional redesign,
new statistics, relational season migrations or deployment automation is a separate
scope and may increase it. Commit boundaries may change as the first slice exposes
coupling; update the queue rather than forcing a fixed count.

During migration, legacy pages and AJAX endpoints remain usable while new APIs
and preview frontend routes are introduced. Migrate a complete workflow before
switching its public routes. Preserve existing canonical URLs where possible;
record intentional redirects and real missing-resource status codes. Remove old
HTML-producing endpoints, template tags, templates, jQuery/widgets and exclusive
form/styling dependencies only after their replacements and callers are verified.

Keep backend regression tests, add schema/API tests, frontend type/component tests
and real-browser workflows. Cover browser-rendered content/navigation, mobile usability and interactions. Continue synthetic isolated PostgreSQL and offline NHL mocks.
Frontend checks join push/PR CI; Python coverage retains its existing meaning and
gate rather than being presented as JavaScript coverage.

## Decisions to resolve before their implementation phase

1. Rendering choice resolved on 2026-11-10: Vue/Vite browser-only application;
   functionality first with mobile usability included in each workflow.
2. Decide whether Django admin is an explicitly allowed internal HTML exception.
   Literal zero Django HTML requires replacing/retiring admin; do not silently
   remove an operational tool or claim the goal complete while it remains.
3. Decide the desired visual direction and first reusable components before broad
   page styling. Functional migration does not authorize unrelated behavior changes.
4. Confirm public production URLs/origin and media paths before route cutover.
   Deployment activation/rehearsal and ambiguous legacy-data review stay deferred.

All public auth/recovery pages and API error responses are within the migration.
Browsable API/Swagger HTML must not be accidentally exposed by JSON-only API
routes; development documentation UI and transactional email rendering are explicit
scope decisions rather than reasons to retain public Django page rendering.

## References

Use the LMS projects as architectural references, not an application starter clone:

- [Frontend tooling](https://github.com/tough-dev-school/lms-frontend-v2/blob/main/apps/frontend/package.json), [frontend conventions](https://github.com/tough-dev-school/lms-frontend-v2/blob/main/apps/frontend/readme.md), and [OpenAPI generation](https://github.com/tough-dev-school/lms-frontend-v2/blob/main/apps/frontend/kubb.config.ts).
- [Django API configuration](https://github.com/tough-dev-school/education-backend/blob/master/src/core/conf/api.py) and [backend service organization](https://github.com/tough-dev-school/education-backend/blob/master/README.md).
- [Vue framework guidance](https://vuejs.org/guide/quick-start), [Nuxt rendering modes](https://learn.nuxt.com/en/concepts/rendering-modes), and [DRF session authentication](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication).

The application-specific contract is in [API conventions](api-conventions.md).


## Implemented TypeScript client foundation

The [generated client workflow](typescript-client.md) pins Node/pnpm and Kubb,
checks all reviewed operations and owns the same-origin session/CSRF transport.
Client generation, TypeScript contracts and mocked transport tests run in a separate
CI job. The [Vue/Vite scaffold](../frontend/README.md) is now implemented;
scoreboard/game page migration follows.


## Implemented scoreboard pilot

The [Vue saved scoreboard](vue-scoreboard.md) is implemented at `/games`, with
API-driven Pacific date discovery, explicit-date preservation, query-based
pagination, conservative saved-state labels and cancellable loading/error recovery.
Desktop/mobile browser regressions cover navigation and failure recovery. Existing
Django routes remain available. Game detail/card navigation is the next slice;
automatic refresh and deployment cutover remain separate work.


## Implemented game-detail pilot

[Vue game details](vue-game-detail.md) now read saved summaries and all six roster
groups at `/games/{nhl_id}`. Scoreboard links preserve date/page context. TOI,
percentages, null/zero and availability semantics come from typed game fields,
without profile/season fallbacks. Responsive tables scroll inside the page and
retain keyboard access. Browser/component checks cover navigation, units, missing
records and retry/cancellation. Automatic saved-data refresh is the next focused
slice; legacy route cutover remains separate.


## Implemented saved-data refresh

The [Vue refresh workflow](vue-refresh.md) completes the scoreboard/game pilot:
visible/online views check saved APIs every minute, preserve last-good data and
focus/scroll, and back off failed checks to five minutes. Timeouts/cancellation,
manual/pause controls and distinct save/check/state-observation semantics are
covered by component/browser regressions. Legacy Django refresh behavior remains
operational. Next follow the recorded session/CSRF/login/logout UI phase, then
registration/recovery and Players tables; deployment cutover remains separate.


## Implemented session-auth UI foundation

The [Vue sign-in workflow](vue-session-auth.md) now bootstraps CSRF/session state,
renders shared header identity and supports login/logout with exact credentials,
token rotation, safe local returns and read-only reconciliation of uncertain POSTs.
No mutations are automatically replayed. Tokens remain in memory, while app-owned
identity/revision state provides a boundary for later private views. Public routes
stay usable; next implement registration UI, then password recovery. Production
route/auth activation decisions remain separate.


## Implemented registration UI

[Vue registration](vue-registration.md) now uses the existing API at `/register`,
with typed field errors, shared auth action serialization, uncertain-result
reconciliation and an explicit sign-in handoff. Creating another account does not
replace the caller's identity/token or silently sign in. Desktop/mobile and
component regressions cover the workflow. Password-reset request/confirmation UI
is the next focused slice; deployment cutover remains separate.


## Implemented password-recovery UI

[Vue password recovery](vue-password-recovery.md) completes the auth UI phase with
generic email acknowledgement, transient fragment capture before routing,
non-consuming validation, correctable password fields and explicit post-reset
sign-in. Session reconciliation and uncertain-write handling never replay mail or
password changes. Desktop/mobile regressions cover URL/history/storage privacy,
reload and same-document links. Next implement the season-scoped Players catalogue;
production mail/rate-limit activation and route cutover remain separate.


## Implemented public Players catalogue

The [Vue Players catalogue](vue-players.md) at `/players` reads loaded season
metadata, season-specific statistics and full filter metadata through the typed
client. Skater totals/averages, goalie rates, numeric/categorical filters, ordering
and pagination preserve their applied URL state. Unknown values remain distinct
from zero; explicit empty seasons never fall back. Aborted/stale reads cannot
replace a newer selection, and wide tables remain within the mobile viewport.
Next add public player profiles, season history and gamelogs with catalogue return
context. Private resources and production route cutover remain later work.


## Implemented public player profiles and history

[Typed player profiles](vue-player-profiles.md) now link from catalogue names,
keeping the full validated catalogue return context. Biography/current team,
selected-season statistics, independent career packets and paginated exact team
contributions retain the backend's null/availability semantics. History failures
leave confirmed profile data visible; cancelled/stale reads cannot replace a new
selection. Desktop/mobile workflows cover typed goalie/skater identity, season/mode,
URL pagination and recovery. Next implement verified saved gamelogs and contextual
game links; team/private screens and production cutover remain later work.


## Implemented verified saved player gamelogs

[Player gamelogs](vue-player-gamelogs.md) now use typed saved row statistics with
actual game PP/SH TOI, explicit unknown/unlinked evidence and goalie rates.
All-saved scope is independent of the profile default season; explicit season/date/
team/statistic filters, ordering and pagination preserve URL state. Validated return
context connects game detail, gamelog, profile and catalogue without forwarding
browser context to APIs. Desktop/mobile, cancellation/deadline and recovery checks
cover the read-only flow. Next add public team browsing and exact team-season
contributions; private/account screens and production cutover remain later work.


## Implemented public teams and scoped season contributions

[Vue teams](vue-teams.md) now provide a saved-identity directory and team detail
with exact season contributions, skater totals/averages and goalie rates. Historical
identities/current metadata do not imply active status or historical reconstruction.
Global loaded-season defaults, explicit empty-season retention and missing/zero
semantics match the existing API. Scoped filters/order/pagination preserve URL state
without borrowing global facets or calculating team values from overall statistics.
Player profiles accept validated team-table return context alongside catalogue
returns. Desktop/mobile and read-failure/cancellation checks cover the flow. Next
implement private Favorites loading with identity/ownership/cache boundaries, then
comparison/private player fields; account/search and production cutover remain later.
