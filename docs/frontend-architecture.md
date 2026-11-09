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

The recommended working baseline is **Nuxt with Vue 3 and TypeScript**:

- Render initial public player/team/game/catalogue content in the frontend
  runtime, then update filters, sorting and live statistics in the browser.
- Render private favorites/comparison/account screens in the browser. Keep
  personal state separate from shared public page data and caches.
- Django renders no public application pages in the completed migration. Nuxt
  server rendering is frontend code executing in a frontend runtime, not Django
  templates. Browser-only rendering remains the alternative if that is the
  intended meaning of "all HTML on the frontend".

The user requested a comparison and has not explicitly finalized the rendering
choice. **Confirm Nuxt hybrid versus a Vue/Vite browser-only app before scaffolding.**
Record any change here; both use the same Django JSON contracts. Nuxt's frontend
runtime, caching and hydration are additional deployment/test responsibilities.
A plain Vue/Vite app can be hosted as static files but needs separate consideration
for public indexing and per-page link metadata.

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
and lockfile, and the existing uv-managed backend. No frontend directory or new
runtime dependency is introduced by this planning commit. Pin compatible tool
versions when scaffolding; do not copy a reference repository's dependency list.

The proposed frontend uses Nuxt/Vue/TypeScript, pnpm, ESLint/Prettier, Vitest and
Playwright. Use Nuxt's SSR-aware data-loading conventions for initial rendered
pages. Evaluate Vue Query only where shared browser caching/mutations justify it;
do not create two competing sources of cached page data. Pinia is optional if
substantial client-only shared state emerges. TanStack Table is the proposed
statistics-table engine; styling uses Tailwind and shared accessible components.
Storybook/visual snapshots can follow once reusable components exist.

Django REST Framework supplies the API, drf-spectacular its OpenAPI schema, and a
pinned generator supplies TypeScript types/client functions. Kubb is the reference
candidate; validate compatibility with Nuxt before selecting generated query hooks.
Generated code must be reproducible from a checked schema without a live NHL
connection or application database.

Use one public origin: route `/api/v1/` to Django, frontend routes to the frontend
build/runtime, and media to the configured storage/web server. Development uses a
proxy to preserve cookie/CSRF behavior. Separate repositories, cross-origin browser
authentication and independent breaking release cycles are not needed initially.
Deploy Nuxt's production output rather than its development server.

## Authentication and cache ownership

Retain Django session authentication and existing accounts. Add JSON CSRF/session
bootstrap, login/logout, registration, recovery and account endpoints; enforce
CSRF on login as well as authenticated unsafe requests. The session cookie remains
HTTP-only, with deployment security attributes configured for the public origin.
Do not introduce JWT/local-storage tokens simply because the UI is separate.

Public responses contain public statistics only. Load favorite/comparison flags
and notes through private endpoints. Personal responses are private/no-store;
public SSR output must not contain another account's state. Do not forward a
visitor's cookies into a shared public cache. Clear private frontend state on
logout or account changes, cancel superseded requests, and prevent older reads
from restoring pre-mutation selections. Preserve the existing user-row quota lock.

Frontend API reads use saved statistics. Preserve current freshness semantics:
save time differs from check time, missing fields differ from zero, and successful
polling does not establish NHL source freshness. Retry public reads with bounds;
mutation retry semantics must be explicitly defined and tested.

## Migration sequence and commit budget

Each range is an estimate for small, reviewable commits, not a single broad patch.
The first concrete queue is: this document/API conventions, API foundation/schema,
frontend scaffolding, generated-client checks, then a scoreboard/game API/UI pilot.

| Phase | Estimated commits | Acceptance evidence |
| --- | --- | --- |
| Architecture and API conventions | 1 | Reviewable decisions, open questions and migration contract |
| API foundation, JSON errors, schema/client generation, frontend scaffold/CI | 3–4 | Schema validation, type/lint/unit checks, production build |
| Scoreboard/game JSON APIs and frontend pilot | 4 | Date/roster/statistics contracts, initial HTML, polling/failure recovery |
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
and real-browser workflows. Cover initial public HTML and metadata as well as
hydrated interaction. Continue synthetic isolated PostgreSQL and offline NHL mocks.
Frontend checks join push/PR CI; Python coverage retains its existing meaning and
gate rather than being presented as JavaScript coverage.

## Decisions to resolve before their implementation phase

1. Finalize hybrid Nuxt versus browser-only Vue/Vite before scaffolding.
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
