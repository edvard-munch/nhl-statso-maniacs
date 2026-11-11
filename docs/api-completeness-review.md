# API completeness review before Vue/Vite

Reviewed: **2026-11-11**, against the checkout at `bc98a25` (search APIs included).
This is a workflow/contract review, not an implementation or deployment change.

## Verdict

**The principal API families exist and the backend foundation is ready for client
work. Full replacement-page parity is not yet complete.** Scaffolding Vue/Vite
would be technically possible, but the agreed API-first order should close the
four contract gaps below before that application commit. Existing pages must not
be switched off just because a matching API route family exists.

The current OpenAPI 3.0.3 export validates with `--validate --fail-on-warn`:
**31 documented paths, 39 operations** (21 GET, 6 POST, 5 PUT, 1 PATCH, 6 DELETE).
The public schema-serving route is intentionally omitted from its own document;
HEAD/OPTIONS and the catch-all 404 route are not extra documented operations.
The [generated TypeScript client](typescript-client.md) is implemented; there is no Vue application yet.

## Scope and evidence

Reviewed legacy [application routes](../players/urls.py), [account/auth routes](../nhl_web_app/urls.py),
[views](../players/views.py), [templates](../players/templates/players/),
[table projection/filtering](../players/player_table.py), existing browser/API tests,
[API routes](../nhl_web_app/api/urls.py), serializers/services, the exported schema,
[frontend architecture](frontend-architecture.md) and [CI workflow](../.github/workflows/tests.yml).

The review used source inspection and an offline schema export. The **39 API
foundation tests pass** using the dedicated synthetic PostgreSQL database. The last
full search-iteration gate was **2019 passed, 48 deselected, 93.97% players
line/branch coverage**; this documentation review did not rerun that entire suite
or alter that measurement. Schema exports were temporary review artifacts.

No application database, live NHL endpoint, email delivery, loader, worker or
production deployment was inspected or executed. Hosted CI/pushed/deployed state
and real legacy-data population are not established by this review.

## Workflow matrix

Paths below are relative to `/api/v1/`. “Covered” means the backend data/action
contract exists; it does not mean the replacement UI/browser workflow is built.

| Existing workflow | Implemented API/composition | Assessment |
| --- | --- | --- |
| Home, About, anonymous bookmark prompt | Static Vue content and links | No data endpoint needed; preserve/redirect routes deliberately. |
| Scoreboard day results and polling | `games/?date=...`, typed game/score/freshness DTOs | Core read covered; saved-date navigation and live-state marker are gaps G2/G3. |
| Game page/rosters and polling | `games/{nhl_id}/` | Rosters, verified stats, null/zero semantics and freshness covered; G3 applies to state presentation. |
| Loaded-season selector | `seasons/` | Covered; use `meta.default_season_id`, not the browser's calendar year. |
| Players totals/averages/goalies, search, filters/order/paging | `players/` with typed/mode/season and named filters | Rows/actions covered; filter option/range discovery is gap G1. |
| Teams index and team-season contributions | `teams/`, `teams/{nhl_id}/`, `teams/{nhl_id}/players/` | Covered; forwards/defencemen/goalie groups use documented typed/position queries. |
| Player biography, video URL, season/team history, career statistics | `players/{player_type}/{nhl_id}/` and `/seasons/` | Covered for agreed statistics; projection panel requires decision D1. Video URL rendering needs an allowed-provider/link policy. |
| Individual gamelog and last-games panel | `players/{player_type}/{nhl_id}/gamelog/` | Covered; last games is a date-descending first page. Do not copy the legacy date-row trust/formatting shortcuts. |
| Favorites selected-season tables, missing-season members and removal | `me/favorites/`, typed membership PUT/DELETE | Covered by private lists/actions; filters need G1 or explicit complete-private-list composition. |
| Aggregated Favorites gamelog | `me/favorites/gamelog/` | Core rows/filtering/paging covered; named player-identity ordering is gap G4. |
| Comparison season/career modes, add/remove/typed reset | `me/comparison/` and typed group/member resources | Covered; transpose typed rows in Vue. Career's empty teams array is deliberate; see composition notes. |
| Private note and position editor | `me/players/{player_type}/{nhl_id}/note/` and `/positions/` | Covered, including legacy ambiguity/conflicts and official-position fallback. |
| Search/full results/typeahead | `search/`, `search/suggestions/` | Covered, with intentional ranking, abbreviation and bounded-preview differences documented in the search contract. |
| CSRF/session/login/logout/registration | `auth/csrf/`, `/session/`, `/login/`, `/logout/`, `/register/` | Covered; browser same-origin/proxy and stale-private-state behavior still need integration tests. |
| Recovery request/token validation/confirmation | `auth/password-reset/`, `/validate/`, `/confirm/` | API covered; frontend-link configuration and delivery/throttling are pre-cutover work D3. |
| Account name/email/measurement edits | `me/` GET/PATCH | Covered; omitted-field, session and normalized-name behavior is tested. |
| Profile image upload/default reset | `me/image/` PUT multipart/DELETE | Covered, with bounded API validation, storage lifecycle and documented cleanup limits. |
| Django admin, debug UI, old OAuth callback | Not ordinary public API replacements | Scope/retirement decisions D2/D4; no removal is authorized by this review. |

Supporting endpoint details are in [API conventions](api-conventions.md) and the
linked family contracts. Existing HTML/AJAX payloads that contain labels, table
cells or templates are **not** suitable JSON fallbacks for missing contracts.

## Contract gaps and focused fixes

### G1 — Players filter metadata (implemented after review)

**Resolved for public Players:** `/api/v1/players/filters/` now supplies complete
structured options and initial/filtered numeric ranges. See the
[implemented contract](players-api.md#complete-filter-metadata). Private scoped
facets still need explicit composition. The observations below describe the
review snapshot before this implementation.

Legacy `player_table.build_table()` publishes `all_teams`, `all_nations`,
`all_positions`, initial/current age/weight/height ranges and available height
values. The UI consumes these in `updatePlayersFilters()` in
[sorter_players.js](../players/static/players/sorter_players.js). The JSON
[query serializers](../players/api/catalogue_serializers.py) accept the corresponding
filters, but `CatalogueMetaSerializer` exposes only season/type/mode/ordering.
There is no equivalent facet/range resource in the exported schema.

A Vue table cannot recover the global choices/ranges from one paginated result.
`teams/` is not a substitute: selected-season participation, historical team
abbreviations, available nations and position labels come from the season
population, not simply the current team registry.

Proposed commit: **Add season-scoped Players filter metadata.** Decide/document
whether to use a dedicated resource or bounded metadata alongside the list. Return
plain structured codes/labels/ranges, not checkbox HTML. Define which filters affect
each facet; preserve the distinction between initial population and currently
filtered ranges instead of accidentally using only the current page. Reuse the
verified season reader, canonical units and empty/missing-value rules.

Acceptance: more than one page, zero/unknown numeric values, historical/multi-team
rows, unknown team metadata, empty seasons, typed/rookie filters, facet selection
semantics, read-only bounded queries and schema tests. Favorites can reuse a
private scoped contract or derive facets from a deliberately complete private
collection; never derive them from an arbitrary visible page.

### G2 — Saved game-date navigation (implemented after review)

**Resolved:** `/api/v1/games/dates/` now provides paginated saved dates, explicit
selection/fallback, adjacent saved dates and a six-date window. See the
[implemented contract](game-dates-api.md). The observations below describe the
original review snapshot.

Legacy `games()` reads `Gameday`, chooses a saved-date fallback when a requested
day is absent, and `utils.get_adjacent()` supplies a six-date saved-day window.
The JSON [scoreboard contract](scoreboard-api.md) deliberately requires an exact
date and returns an empty collection for a valid unsaved day. No resource supplies
available/adjacent/latest saved dates. `seasons/` is SBS-season discovery, not game
calendar discovery.

Proposed commit: **Add read-only saved game-date discovery/navigation.** Keep
`games/?date=...` exact-date behavior intact. Provide an explicit saved-date window
and/or adjacent/latest metadata with canonical Pacific schedule dates, bounded
paging and empty-store behavior. Alternatively, explicitly approve a calendar-only
UI that drops the saved-date strip/fallback; that would be a UX change, not existing
API parity.

Acceptance: noncontiguous dates, empty store, edges/windows, valid unsaved days,
invalid dates, timezone semantics, bounded queries, no loader calls/writes.

### G3 — Saved game-state evidence (implemented after review)

**Resolved for conservative legacy evidence:** shared game summaries now expose
a typed state/source/observation/conflict object. See the
[implemented contract](game-state-api.md). Qualified scheduler observations remain
a separate future enhancement. The observations below describe the review snapshot.

Legacy `upd_gms.get_score()` stores ` (Live)` in `Game.result`, and the scoreboard
renders that result string. The new [score projection](../players/api/scoreboard.py)
recognizes the suffix while parsing scores but returns only scores, OT/SO outcome
and `is_final`. `ScoreboardGameSerializer` has no live/state field. A nonfinal game
is not necessarily live; neither a zero score nor a fresh API check proves it is.

Proposed commit: **Expose explicit saved game-state evidence.** Specify state,
source and observation/freshness semantics, with unknown/ambiguous values kept
explicit. Choose between conservatively verified legacy result evidence and a
properly qualified scheduled-game observation; do not silently equate their ages.
Do not return a raw result string and make Vue parse it, or infer live from
`is_final=false`. Reuse the contract wherever game summaries are embedded.

Acceptance: live, final, scheduled/nonfinal, stale/missing/conflicting evidence,
malformed result/side data and no writes/upstream requests. Start times, period and
clock are potential enhancements; this review did not find them in the existing
public page UI and does not classify them as missing parity requirements.

### G4 — Favorites gamelog player-identity ordering (implemented after review)

**Resolved:** the aggregated Favorites gamelog now accepts `player_name`,
`player_last_name` and `player_nhl_id` ordering, globally before pagination. See the
[implemented contract](favorites-gamelog-api.md#player-identity-ordering). Public
single-player ordering remains unchanged. The observations below describe the
original review snapshot.

The legacy aggregated table includes a player-name column and supports sorting it.
The new [Favorite gamelog](favorites-gamelog-api.md) includes identity and a name
search, but inherits `GamelogQuerySerializer` and `player_logs.ordering_fields()`:
allowed identity keys are date/game/team/opponent, not player name/NHL ID. Its
internal name/ID tie-breakers do not provide an explicit user-selected name sort.

Proposed commit: **Add named player-identity ordering to the aggregated Favorites
gamelog.** Add allowlisted name/last-name/NHL-ID keys to this resource, define ties
with player type and date/game evidence as applicable, and preserve global sorting
before pagination. Do not “fix” this by sorting one downloaded page in Vue or by
allowing arbitrary JSON/ORM field paths. The individual public gamelog need not gain
meaningless cross-player sorting parameters.

Acceptance: multiple favorites/pages, equal names, typed IDs, ascending/descending,
unknown evidence, query limits, private ownership and schema coverage.

## Composition that already works

These are implementation considerations, not reasons to create duplicate endpoint
families:

- **Favorite/comparison buttons:** load both typed private lists, follow all pages
  and build sets keyed by `(player_type, nhl_id)`. Public player/team/game/search
  DTOs intentionally omit these flags. Comparison-to-favorite buttons use that same
  private membership cache. Normal quotas bound the data, but preserved over-limit
  legacy rows still require following `next`. A lean membership-snapshot API could
  reduce payload later; it is an optimization, not a current functional blocker.
- **Private positions/notes:** fetch typed private detail resources for the profile
  panel, using their `source` and fallback values. The legacy Players table uses
  official position data, not a private override; this review does not require
  private overrides to alter public filtering/ranking. Do not issue per-row private
  requests across a catalogue just to render existing public columns.
- **Measurement preference:** obtain it from `me/`, format canonical public values
  in Vue and select the corresponding named numeric filter units. Null means unknown;
  do not write converted statistics back to players or vary shared public responses
  by the viewer's preference. G1 supplies the global range/options prerequisite.
- **Career comparison team labels:** the legacy comparison builds team labels from
  its selected-season projection even in career mode. Career API queries deliberately
  have `season_id=null` and empty teams. If preserving that row, compose with the
  same typed selection's season query and label it as season participation; do not
  treat it as a career team or silently replace it with the current biography team.
- **Last-games panels, time/percentage formatting and grouping:** existing numeric
  gamelog/season DTOs and typed roster groups supply the data. Format seconds and
  fraction rates in Vue; keep formulas/averages on the backend. Use `saved_at` for
  saved-data age; API `checked_at` does not prove a new NHL fetch.
- **Preview search/full-results action and external player links:** Vue builds
  grouping/navigation from typed identities and encoded query strings. Do not
  recreate HTML sentinels. The profile video URL is exposed, but an allowed-provider
  iframe policy or safe external-link choice belongs to its UI slice; retired video
  ingestion/OAuth must not be restarted implicitly.

## Decisions and cutover work

### D1 — Legacy projections need an explicit decision

The [legacy audit](legacy-audit.md) retains stored `proj_stats` pending a separate
product/provenance decision. The profile template still contains projected panels,
although the view gates them through `season_in_prog()` with the stale hardcoded
`SEASON_ENDS` in April 2024. That gate being false now does not establish that the
feature/data was deliberately retired. Profile API serializers do not expose it.

Before claiming full profile parity, either define a trusted season/source/validity
contract and API, or explicitly approve retiring the panel while preserving data
until a separate cleanup. Do not copy unscoped JSON, compute guessed projections
in Vue, restore the retired loader or remove stored data during scaffolding.
This decision need not block a scoreboard-only preview.

### D2 — Literal “Django generates no HTML” still includes admin

Django admin and existing public templates are still routed. The migration plan
already calls for a decision whether admin is an internal HTML exception. Obtain
that decision or plan a separate replacement/retirement; do not silently remove
an operational tool or call the API-only goal complete while it remains unresolved.
Browsable API/Swagger HTML is not exposed by the new API; debug UI is a separate
local-development boundary.

### D3 — Recovery/operational auth readiness precedes public auth cutover

Configure `PASSWORD_RESET_PUBLIC_ORIGIN` and a real Vue
`PASSWORD_RESET_FRONTEND_PATH`; blank frontend path intentionally points new JSON
emails at the existing HTML confirmation route. Preserve a deliberate plan for
previously issued reset links. Vue must handle UID/token exchange, CSRF, expiry,
reuse and logout/account-change cache clearing, rather than relying on Django HTML.

Recovery delivery is synchronous and response timing can distinguish work paths;
[the existing contract](password-recovery-api.md) records this. No application
throttle configuration was found in `REST_FRAMEWORK`; external proxy protection
was not inspected. Delivery/timing and abuse controls remain pre-public-auth-cutover
work, not a reason to block installing a frontend toolchain. No deployment/email
configuration or real-account test was performed during this review.

### D4 — Explicit route and UX retirement choices

Keep current public URLs working until replacement browser flows pass. Decide how
to handle static Home/About/bookmark prompts and the old `auth_callback/` route
(the latter points to the retired console OAuth flow and is not a new API auth
requirement). Admin/debug/media/API routes must not be swallowed by a SPA fallback.
Page sizes above the API's 100-row cap and legacy “all” controls need an explicit
UI choice or deliberate multi-page retrieval, not an undocumented limit bypass.
Known intentional API changes such as strict dates, unavailable-value semantics,
search ranking and bounded image formats must be reflected in UI acceptance tests.

## Schema/client/CI readiness and recommended queue

The [reviewed offline schema workflow](openapi-workflow.md) is now implemented,
with a checked `api/openapi.json` and a separate database-free drift-check CI job.
The [TypeScript client foundation](typescript-client.md) now has a frozen pnpm
lockfile, checked SDK, transport tests, compilation and generation drift CI checks.
There is still no Vue/Vite application. `browser/package.json` remains the existing
npm/Playwright legacy smoke harness. Vue component/build checks follow scaffolding;
existing backend/schema contracts and legacy Chromium flows remain covered.

Recommended focused commits, following the user's API-first preference:

1. **Season-scoped Players filter metadata** (G1) — implemented for public Players.
2. **Saved game-date discovery/navigation** (G2) — implemented.
3. **Explicit saved game-state evidence** (G3) — implemented for legacy sources.
4. **Aggregated Favorites gamelog identity ordering** (G4) — implemented.
5. Record projection/admin decisions before their affected cutovers. Reviewed
   schema export/drift checks and reproducible TypeScript client generation are
   implemented.
6. Introduce Vue/Vite/TypeScript with pinned compatible tooling, same-origin dev
   proxy and frontend CI; then migrate the scoreboard/game pilot at desktop/mobile
   sizes. Keep dependencies and page implementation in focused commits.

Do not select a generator merely because it emits TypeScript. Verify enum/null and
polymorphic-statistics handling, session cookies/CSRF, typed 403 errors, multipart
upload/reset, encoded pagination and response/request cancellation. Anonymous
bootstrap uses `auth/session/`, not the authenticated API version root. Proxy errors
outside Django are not guaranteed JSON. Client reproducibility/type checks should
run offline from a reviewed schema, with no NHL/application database dependency.

**Completion gate:** G1–G4 are implemented or have an explicitly approved UX
alternative; the affected decisions/configuration are resolved; and each migrated
workflow has desktop/mobile browser evidence before route cutover. This review
changes documentation only. Endpoint fixes, removals, frontend scaffolding and
deployment remain separate tasks.
