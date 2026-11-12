import { expect, test, type Page } from './fixtures.js';
import { profile, seasonHistory } from '../tests/fixtures/profile.js';
import { catalogue, filterMetadata, loadedSeasons } from '../tests/fixtures/players.js';
import { gamelog, gamelogGameDetail } from '../tests/fixtures/gamelog.js';

function queryFor(url: string) {
  const parsed = new URL(url);
  const query = parsed.searchParams;
  query.set('player_type', parsed.pathname.includes('/goalie/') ? 'goalie' : 'skater');
  return query;
}
async function intercept(page: Page) {
  await page.route('**/api/v1/seasons/?*', (route) => route.fulfill({ json: loadedSeasons }));
  await page.route('**/api/v1/players/filters/?*', (route) =>
    route.fulfill({ json: filterMetadata(new URL(route.request().url()).searchParams) }),
  );
  await page.route('**/api/v1/players/?*', (route) =>
    route.fulfill({ json: catalogue(new URL(route.request().url()).searchParams) }),
  );
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/(?:\?.*)?$/, (route) =>
    route.fulfill({ json: profile(queryFor(route.request().url())) }),
  );
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/seasons\/\?/, (route) =>
    route.fulfill({ json: seasonHistory(queryFor(route.request().url())) }),
  );
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/gamelog\/\?/, (route) => {
    const query = queryFor(route.request().url());
    return route.fulfill({
      json: gamelog(query, {
        count: 101,
        next: query.get('page') === '2' ? null : 'https://not-followed.example/next',
        previous: query.get('page') === '2' ? '/ignored' : null,
      }),
    });
  });
  await page.route('**/api/v1/games/2026020001/', (route) =>
    route.fulfill({ json: gamelogGameDetail() }),
  );
}

test('preserves the full catalogue/profile/gamelog return chain through game navigation and reload', async ({
  page,
}) => {
  await intercept(page);
  const cataloguePath = '/players?season_id=20262027&mode=averages&team=BUF&page=2';
  await page.goto(cataloguePath);
  await page.getByRole('link', { name: 'Season Skater', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater');
  const profilePath = new URL(page.url()).pathname + new URL(page.url()).search;
  await page.getByRole('link', { name: 'View selected-season game log', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater game log');
  expect(new URL(page.url()).searchParams.get('season_id')).toBe('20262027');
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  const logPath = new URL(page.url()).pathname + new URL(page.url()).search;
  const first = page.locator('tbody tr').first();
  expect(await first.getByRole('cell').allTextContents()).toEqual(
    expect.arrayContaining(['12:34', '00:00', '01:35']),
  );
  await page.getByRole('link', { name: 'Nov 12 · Game 2026020001', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Game details');
  const roster = page.getByRole('region', { name: 'Away forwards', exact: true });
  await expect(roster).toContainText('01:35');
  await page.reload();
  await page.getByRole('link', { name: 'Back to player gamelog', exact: true }).click();
  await expect(page).toHaveURL(logPath);
  await page.getByRole('link', { name: 'Back to player profile', exact: true }).click();
  await expect(page).toHaveURL(profilePath);
  await page.getByRole('link', { name: 'Back to players', exact: true }).click();
  await expect(page).toHaveURL(cataloguePath);
});

test('keeps all-saved scope, unlinked and undated rows, filter units and URL history explicit', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/players/skater/8480001/gamelog');
  await expect(page.getByText(/All saved seasons and dates/)).toBeVisible();
  expect(new URL(page.url()).searchParams.has('season_id')).toBe(false);
  const orphan = page
    .getByRole('row')
    .filter({ has: page.getByRole('rowheader', { name: 'Nov 10 · Unlinked', exact: true }) });
  await expect(orphan).toContainText('Unverified');
  await expect(orphan.getByRole('link')).toHaveCount(0);
  expect(
    (await orphan.getByRole('cell').allTextContents()).filter(
      (value) => value === '0' || value === '00:00',
    ),
  ).toHaveLength(0);
  await expect(
    page.getByRole('link', { name: 'Date unavailable · Game 2026020002', exact: true }),
  ).toBeVisible();
  await page.getByText('Statistic filters', { exact: true }).click();
  await page.getByRole('spinbutton', { name: 'PP TOI (seconds) minimum', exact: true }).fill('0');
  await page
    .getByRole('combobox', { name: 'Hits availability', exact: true })
    .selectOption('false');
  await page.getByLabel('Schedule date from', { exact: true }).fill('2026-10-01');
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(page).toHaveURL(/pp_toi_seconds_min=0/);
  expect(new URL(page.url()).searchParams.get('hits_isnull')).toBe('false');
  await page.getByRole('button', { name: 'Sort by SH TOI (seconds)', exact: true }).click();
  await expect(page).toHaveURL(/ordering=-sh_toi_seconds/);
  await page.reload();
  await expect(page.getByLabel('Schedule date from', { exact: true })).toHaveValue('2026-10-01');
  await page.goBack();
  await expect(page).not.toHaveURL(/ordering=/);
  const width = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
  await expect(
    page.getByRole('region', { name: 'Saved player gamelog', exact: true }),
  ).toHaveAttribute('tabindex', '0');
});

test('shows goalie rates and decision without skater fields and preserves public sign-in context', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/players/goalie/8480001/gamelog?season_id=20262027');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Goalie game log');
  await expect(
    page.getByRole('region', { name: 'Saved player gamelog', exact: true }),
  ).toContainText('90.6%');
  await expect(page.getByRole('button', { name: 'Sort by Goals', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Sort by Decision', exact: true })).toBeAttached();
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  expect(new URL(page.url()).searchParams.get('returnTo')).toBe(
    '/players/goalie/8480001/gamelog?season_id=20262027',
  );
});

test('retains explicit empty seasons, clears stale rows after failure and retries the selected query', async ({
  page,
}) => {
  await intercept(page);
  let fail = false;
  await page.route(/\/api\/v1\/players\/skater\/\d+\/gamelog\/\?/, (route) => {
    const query = queryFor(route.request().url());
    if (fail)
      return route.fulfill({
        status: 503,
        contentType: 'text/html',
        body: 'private upstream error',
      });
    return route.fulfill({
      json: gamelog(query, query.get('season_id') === '20272028' ? { count: 0, results: [] } : {}),
    });
  });
  await page.goto('/players/skater/8480001/gamelog?season_id=20272028');
  await expect(
    page.getByText('No saved gamelog rows match this selection.', { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL('/players/skater/8480001/gamelog?season_id=20272028');
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(
    page.getByRole('rowheader', { name: 'Nov 12 · Game 2026020001', exact: true }),
  ).toBeVisible();
  fail = true;
  await page.getByRole('button', { name: 'Sort by Date', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Unable to load this saved gamelog');
  await expect(page.locator('tbody')).toHaveCount(0);
  await expect(page.getByText('private upstream error')).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(
    page.getByRole('rowheader', { name: 'Nov 12 · Game 2026020001', exact: true }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.has('ordering')).toBe(true);
});
