# Offline Chromium smoke tests

Seven browser cases check real JavaScript, DOM events and Django AJAX responses:

- Players season selection, totals/averages and goalie modes, and unloaded seasons.
- Goalie-only and empty favorites, including an old season with no goalie data.
- Favorites skater totals/averages before and after changing season.
- Comparison season/career modes, mode preservation across season changes,
  player removal, group reset confirmation and the resulting empty state.

Conflicting snapshot values ensure displayed assertions use the correct sources.
Browser JavaScript errors and HTTP errors on AJAX responses fail the tests (normal
redirects are followed). Stored player columns must remain unchanged. Authenticated
cases use a synthetic Django test session, not an application account, and check
that other users' saved memberships remain intact after real mutations.

The Python environment is unchanged. Browser tooling uses the separate, locked
Node package in `browser/` (Node 22+, validated with Node 24 and Playwright 1.56.0).
The tests run against pytest-django's live server and a migrated **test database**,
with synthetic fixtures. Never start them against your application database.

## Setup

Activate the project venv and configure the dedicated test role/configuration in
[testing.md](testing.md), including ignored `test-database.local.json`. Then run
from the repository root:

```bash
npm --prefix browser ci --ignore-scripts
python scripts/prepare_browser_assets.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/.browser-cache/browsers" \
  npm --prefix browser exec -- playwright install --no-shell chromium
make test-browser
```

Dependency/browser/asset installation requires network access. On Linux machines
missing Chromium system libraries, Playwright's `install --with-deps --no-shell
chromium` installs them; CI uses this option. See the [official browser setup](https://playwright.dev/docs/browsers).
The command above uses the full Chromium browser in headless mode, not the separate
headless shell.

The asset preparation script downloads the **same pinned CDN versions already
used by the app**, checks committed SHA-256 hashes and caches them under
`.browser-cache/assets`. Chromium is cached under `.browser-cache/browsers` and
Node dependencies under `browser/node_modules`; these paths are ignored by Git.
Repeated asset preparation needs no network when cached checksums match. If the
app's CDN versions change, review/update the manifest with those versions and
checksums; tests do not substitute fake jQuery/tablesorter implementations.

## Execution and isolation

`make test-browser` uses `scripts/run_hook_tests.py --browser`: the same dedicated
test configuration/credential overrides as local hooks, with `browser and not
external` selection. Browser and coverage modes cannot be combined. Default
`make test`, coverage targets and commit/push hooks exclude both `external` and
`browser`, so they do not require Node, Chromium or asset downloads.

During a browser test, only requests to the temporary live-server origin are
allowed through. Required third-party scripts and core CSS are served from the
checksum-verified cache. Other external styles and image/font decoration are
suppressed. Unexpected external script/document/API requests fail the test, and
server-side requests through `requests` are blocked. These are functionality smoke
checks, not pixel/visual or CDN-availability tests.

There are no fixed sleeps: checks wait for table cells and AJAX completion. The
Node subprocess has a bounded timeout. Failures save screenshots and Playwright
traces to ignored `browser-artifacts/`; open a trace with:

```bash
npm --prefix browser exec -- playwright show-trace browser-artifacts/modes.zip
```

## CI and remaining work

The existing push/PR workflow runs the offline coverage gate first, installs the
locked browser toolchain/assets, then runs all seven browser checks separately
against the ephemeral PostgreSQL service. Failure artifacts are uploaded when
present. The coverage report remains the offline server-side result; browser runs
do not inflate it. Hosted execution still needs confirmation after pushing.

The shared harness handles cached assets, blocked external requests, synthetic
session cookies, AJAX completion and failure artifacts for both suites. Favorites
gamelogs intentionally span all stored seasons; season-dependent requests must
retain the selected season. Missing-season players remain listed with dashes and
a visible status label. A browser case exposed a status label discarded outside
legacy table-cell markup; that name/status cell now uses valid HTML fragments.

Team joined/split controls and additional favorites mutations remain later focused
browser work. Browser login, concurrent quota enforcement and migration of legacy
GET-based mutations to POST are not established by these smoke cases.
