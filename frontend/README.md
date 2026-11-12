# Vue frontend

Vue 3, Vue Router, Vite and TypeScript live alongside the uv-managed Django
backend. The responsive shell, home/missing-page routes and generated client now
include a [saved scoreboard](../docs/vue-scoreboard.md) at `/games`, with exact
date selection, navigation, pagination and error recovery.
[Game details](../docs/vue-game-detail.md) at `/games/{nhl_id}` show saved rosters
and game statistics with scrollable mobile tables. Both views include
[automatic saved-data refresh](../docs/vue-refresh.md), pause/manual controls and
last-check feedback. [Sign-in](../docs/vue-session-auth.md) at `/login` shares
Django sessions, with header identity/logout, safe return navigation and CSRF
rotation/reconciliation. [Registration](../docs/vue-registration.md) at `/register`
shows validation and explicit sign-in confirmation without switching the caller
session.
Existing Django pages and production routing are unchanged.

## Run locally

Use Node **24.13.0**, Corepack and the pinned pnpm **10.34.9**. From the project root:

```bash
make frontend-sync
```

Start Django using your existing shortcut or, in a separate terminal:

```bash
uv run --locked python manage.py runserver 127.0.0.1:8000
```

Then start Vite:

```bash
make frontend-dev
```

Open **http://127.0.0.1:5173/**. The legacy website is still on
http://127.0.0.1:8000/. Django needs its normal local environment/database settings;
the frontend shell and its automated tests do not require a running backend.
Open `/games` to browse saved data from Django. The dev server binds to loopback
and fails if its port is already in use.

Vite forwards only `/api/v1/` (including its version root without the final slash)
and `/media/` to Django. Paths, Host, Origin, Cookie, Set-Cookie, CSRF headers,
status codes and content types pass through. Preserving Host and Origin together
keeps Django's same-origin CSRF check intact without enabling CORS or rewriting
cookies. Your local Django `ALLOWED_HOSTS` must include `127.0.0.1` (or the local
hostname you use). Do not disable CSRF checks or production cookie security.

If Django runs on a different local port, copy `.env.example` to `.env.local` and
set `DJANGO_DEV_ORIGIN`, or set that variable in the shell before starting Vite.
Only loopback HTTP(S) origins without credentials, paths, queries or fragments are
accepted. This variable is server-only; never place backend secrets in `VITE_*`
variables, which become public client code. The default media prefix is `/media/`;
custom storage/media URLs need their own routing configuration before integration.

The proxy is for development only. Sessions/cookies from a production host are
not local development sessions. HTTPS-only local cookie settings require a matching
HTTPS development setup; do not weaken deployed settings to support local HTTP.
App startup reads CSRF/session state; `/games` reads the saved-game APIs. API usage follows the
[generated client workflow](../docs/typescript-client.md).

## Checks and build

```bash
make api-client-check frontend-typecheck frontend-lint frontend-format-check
make frontend-test
make frontend-browser-install  # headless Chromium; may need OS libraries on Linux
make frontend-test-browser     # builds current code, then Chromium desktop/mobile
make frontend-build
make frontend-preview          # inspect the static build at 127.0.0.1:4173
```

`make frontend-format` formats handwritten frontend files. Generated SDK/types and
the lockfile are excluded from format/lint mutation; regenerate them from the
reviewed schema. The initial formatter adoption also normalizes existing
handwritten client files without changing their behavior.

Vitest covers scoreboard date/state/error/cancellation behavior, shell
navigation/focus/title, API transport/generation and the real
Vite proxy using a synthetic loopback backend. Chromium tests exercise the actual
built app at desktop and mobile sizes, scoreboard/detail date/page navigation,
roster table scrolling, error recovery, keyboard skipping, deep-link reload and
client-side recovery. Tests never use the application database or NHL services.
CI performs frozen installation, generation drift checks, Vue/TypeScript checks,
lint/format, Vitest tests, production build and Chromium tests. Browser binaries
are an explicit headless-only install; dependency lifecycle scripts remain disabled.

`dist/`, local `.env.*`, browser reports and dependencies are ignored. Production
output is static HTML/CSS/JS, with no server-side Vue rendering. Vite's dev and
preview servers are not deployment servers. Production hosting must serve the
frontend with a route fallback to `index.html`, while routing API/media requests
to their backend/storage first. The client missing-page view does not establish a
server-side 404 status. Production route cutover and hosting remain separate work.

The base stylesheet provides wrapping navigation, touch-sized links and visible
keyboard focus. Shared table components, caching/state libraries and a styling
framework should be introduced when the first real workflows need them.

Tooling references: [Vue TypeScript guidance](https://vuejs.org/guide/typescript/overview),
[Vite proxy options](https://vite.dev/config/server-options#server-proxy),
[Vue Router history deployment](https://router.vuejs.org/guide/essentials/history-mode)
and [Playwright headless installation](https://playwright.dev/docs/browsers#chromium-headless-shell).
