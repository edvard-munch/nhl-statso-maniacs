# Offline Chromium smoke tests

Twenty-one browser cases check real JavaScript, DOM events and Django AJAX responses:

- Players season selection, totals/averages and goalie modes, and unloaded seasons.
- Goalie-only and empty favorites, including an old season with no goalie data.
- Favorites skater totals/averages before and after changing season.
- Removing the last skater or goalie from a mixed list and removing either type
  as the final favorite: updated counts, remaining-group activation, final empty
  state, season retention and persistence after reloading.
- Removing a sole name-filter match while other favorites remain, and removing
  the only row on page two: both skaters and goalies preserve filters, name sorting,
  season and global counts, with valid paging and deletion confirmed after reload.
- Comparison season/career modes, mode preservation across season changes,
  player removal, group reset confirmation and the resulting empty state.
- Team split/joined layouts and independent totals/averages switches, historical
  season selection and unloaded-season empty states. Team-specific skater/goalie
  values must differ correctly from combined totals and stale snapshots.
- AJAX failure and explicit retry for favorites removal, comparison mode/removal/
  reset, and team mode/split-layout changes. A failed split must preserve the
  joined table even when the other request succeeds.

Conflicting snapshot values ensure displayed assertions use the correct sources.
Browser JavaScript errors and unexpected HTTP errors on AJAX responses fail the
tests (normal redirects are followed). Stored player columns must remain unchanged. Authenticated
cases use a synthetic Django test session, not an application account, and check
that other users' saved memberships remain intact after real mutations.

The Python environment is unchanged. Browser tooling uses the separate, locked
Node package in `browser/` (Node 22+, validated with Node 24 and Playwright 1.56.0).
The tests run against pytest-django's live server and a migrated **test database**,
with synthetic fixtures. Never start them against your application database.

## Setup

Run `uv sync --locked` and configure the dedicated test role/configuration in
[testing.md](testing.md), including ignored `test-database.local.json`. Then run
from the repository root:

```bash
npm --prefix browser ci --ignore-scripts
uv run --locked python scripts/prepare_browser_assets.py
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
locked browser toolchain/assets, then runs all twenty-one browser checks separately
against the ephemeral PostgreSQL service. Failure artifacts are uploaded when
present. The coverage report remains the offline server-side result; browser runs
do not inflate it. Hosted execution still needs confirmation after pushing.

The shared harness handles cached assets, blocked external requests, synthetic
session cookies, AJAX completion and failure artifacts for both suites. Favorites
gamelogs intentionally span all stored seasons; season-dependent requests must
retain the selected season. Missing-season players remain listed with dashes and
a visible status label. A browser case exposed a status label discarded outside
legacy table-cell markup; that name/status cell now uses valid HTML fragments.

Three team cases reuse the existing traded-player fixtures and verify actual
team contributions, unique joined rows, both split sections returning together,
mode consistency after splitting and selected-season parameters on every team AJAX
request. Full saved team/player snapshots stay unchanged. No application-code or
asset/dependency changes were needed for these scenarios.

The favorites removal controller uses the server's remaining counts rather than
inferring a globally empty list from filtered table rows. Empty groups are hidden,
the remaining group is activated and a final empty state offers the Players link.
Skater/goalie section wrappers are closed independently so hiding one does not hide
the other. Removal requests retain the selected season; successful updates use a
stable status message. In-flight requests are guarded, and failed/unconfirmed
responses do not remove visible rows. The legacy GET/toggle API is unchanged.

The recovery cases inject six one-shot HTTP 503 responses before requests reach
Django. Only those exact injected requests are exempt from the HTTP-error check;
all other failures still fail the test. Each case checks the error, unchanged
data/mode/counts, usable controls, successful explicit retries and error clearing.
The selected season, other users' memberships and stored player columns are
protected. Retries use real Django responses. These cases do not establish safe
retry after a mutation commits but its response is lost: the legacy GET/toggle
API still needs a separate design decision.

Four filtered/paginated removal cases use 26 synthetic favorites per player type,
plus an opposite-type favorite. Filtered empty results must show the no-match
status while retaining the group; clearing the filter restores remaining players.
Removing page two's final row returns to page one and hides the unneeded pager.
Reload checks reapply filters explicitly; filters are not persisted across reloads.
Database assertions protect other memberships, comparison lists and player fields.

Browser login, concurrent quota enforcement and migration of legacy
GET-based mutations to POST are not established by these smoke cases.
