# Offline Chromium smoke tests

The first browser batch checks the Players page with real JavaScript, DOM events
and Django AJAX responses. It covers changing the season, totals/averages and goalie
modes, and an unloaded season's empty state. Conflicting player snapshot values
ensure assertions use season rows. Browser JavaScript errors and failed table AJAX
responses fail the tests; stored player records must remain unchanged.

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
locked browser toolchain/assets, then runs the three browser checks separately
against the ephemeral PostgreSQL service. Failure artifacts are uploaded when
present. The coverage report remains the offline server-side result; browser runs
do not inflate it. Hosted execution still needs confirmation after pushing.

Favorites goalie-only/empty lists, comparison mode/removal/reset controls and team
joined/split controls remain later focused browser batches. This commit establishes
the harness and Players workflows, and fixes an exposed empty-metadata checkbox
error; it does not establish browser coverage for every saved-list interaction.
