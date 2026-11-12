import { expect, test, type Page } from './fixtures.js';
import { profile, seasonHistory } from '../tests/fixtures/profile.js';
import { catalogue, filterMetadata, loadedSeasons } from '../tests/fixtures/players.js';

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
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/\?/, (route) =>
    route.fulfill({ json: profile(queryFor(route.request().url())) }),
  );
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/seasons\/\?/, (route) => {
    const query = queryFor(route.request().url());
    return route.fulfill({
      json: seasonHistory(query, {
        count: 51,
        next: query.get('page') === '2' ? null : 'https://not-followed.example/next',
        previous: query.get('page') === '2' ? '/ignored' : null,
      }),
    });
  });
}

test('opens typed profiles from the catalogue and returns to the exact applied selection', async ({
  page,
}) => {
  await intercept(page);
  const context = '/players?season_id=20262027&mode=averages&team=BUF&page=2';
  await page.goto(context);
  await page.getByRole('link', { name: 'Season Skater', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater');
  expect(new URL(page.url()).pathname).toBe('/players/skater/8480001');
  expect(new URL(page.url()).searchParams.get('returnTo')).toBe(context);
  await expect(
    page.getByRole('region', { name: 'Selected season and career statistics', exact: true }),
  ).toContainText('Career per-game averages');
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater');
  await page.getByRole('link', { name: 'Back to players', exact: true }).click();
  await expect(page).toHaveURL(context);
  await expect(page.getByRole('searchbox', { name: 'Search name', exact: true })).toBeVisible();
});

test('keeps missing selected statistics, career values and unverified team contributions separate', async ({
  page,
}) => {
  await intercept(page);
  await page.route(/\/api\/v1\/players\/skater\/\d+\/\?/, (route) => {
    const query = queryFor(route.request().url());
    return route.fulfill({
      json: profile(
        query,
        query.get('season_id') === '20272028'
          ? { selected_season: { availability: 'missing', stats: null } }
          : {},
      ),
    });
  });
  await page.goto('/players/skater/8480001?season_id=20272028');
  const statistics = page.getByRole('region', {
    name: 'Selected season and career statistics',
    exact: true,
  });
  const season = statistics
    .getByRole('row')
    .filter({ has: page.getByRole('rowheader', { name: '2027–28 · totals', exact: true }) });
  await expect(season).toContainText('Missing');
  expect(
    (await season.getByRole('cell').allTextContents()).slice(1).every((value) => value === '—'),
  ).toBe(true);
  const career = statistics
    .getByRole('row')
    .filter({ has: page.getByRole('rowheader', { name: 'Career totals', exact: true }) });
  expect(await career.getByRole('cell').allTextContents()).toContain('120');
  const history = page.getByRole('region', {
    name: 'Season history and team contributions',
    exact: true,
  });
  const split = history.getByRole('row').filter({
    has: page.getByRole('rowheader', { name: '2026–27 · BUF contribution', exact: true }),
  });
  await expect(split).toContainText('Unverified');
  expect(
    (await split.getByRole('cell').allTextContents()).slice(1).every((value) => value === '—'),
  ).toBe(true);
  await page.getByRole('button', { name: 'Show 2025–26', exact: true }).click();
  await expect(page).toHaveURL(/season_id=20252026/);
  await expect(statistics).toContainText('2025–26 · totals');
  expect(await career.getByRole('cell').allTextContents()).toContain('120');
  await page
    .getByLabel('Selected season and history statistics', { exact: true })
    .selectOption('averages');
  await page.getByRole('button', { name: 'Apply selection', exact: true }).click();
  await expect(statistics).toContainText('2025–26 · per-game averages');
  const width = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.page).toBeLessThanOrEqual(width.viewport);
  await expect(history).toHaveAttribute('tabindex', '0');
});

test('paginates history through URL/reload/back and recovers from a missing page without hiding biography', async ({
  page,
}) => {
  await intercept(page);
  let fail = true;
  await page.route(/\/api\/v1\/players\/skater\/\d+\/seasons\/\?/, (route) => {
    const query = queryFor(route.request().url());
    if (fail && query.get('page') === '2')
      return route.fulfill({
        status: 404,
        json: { error: { code: 'not_found', message: 'private history detail', fields: {} } },
      });
    return route.fulfill({
      json: seasonHistory(query, {
        count: 51,
        next: query.get('page') === '2' ? null : '/not-followed',
        previous: query.get('page') === '2' ? '/not-followed' : null,
      }),
    });
  });
  await page.goto('/players/skater/8480001?season_id=20262027');
  await page.getByRole('button', { name: 'Next history page', exact: true }).click();
  await expect(page).toHaveURL(/history_page=2/);
  await expect(page.getByRole('alert')).toContainText('Unable to load this history page');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater');
  await expect(page.getByText('private history detail')).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'Retry history', exact: true }).click();
  await expect(page.getByText(/History page 2\./)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/History page 2\./)).toBeVisible();
  await page.goBack();
  await expect(page.getByText(/History page 1\./)).toBeVisible();
});

test('shows goalie rates without averages, safe auth return context and recoverable profile failures', async ({
  page,
}) => {
  await intercept(page);
  let fail = true;
  await page.route(/\/api\/v1\/players\/goalie\/\d+\/\?/, (route) =>
    fail
      ? route.fulfill({ status: 503, contentType: 'text/html', body: 'private proxy detail' })
      : route.fulfill({ json: profile(queryFor(route.request().url())) }),
  );
  await page.goto('/players/goalie/8480001?season_id=20262027&returnTo=https://evil.example/');
  await expect(page.getByRole('alert')).toContainText('Unable to load this saved player');
  await expect(page.getByText('private proxy detail')).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Goalie');
  const statistics = page.getByRole('region', {
    name: 'Selected season and career statistics',
    exact: true,
  });
  await expect(statistics).toContainText('91.5%');
  await expect(
    statistics.getByRole('rowheader', { name: 'Career per-game averages', exact: true }),
  ).toHaveCount(0);
  await expect(page.locator('#profile-mode option[value="averages"]')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Back to players', exact: true })).toHaveAttribute(
    'href',
    '/players',
  );
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  expect(new URL(page.url()).searchParams.get('returnTo')).toContain('/players/goalie/8480001?');
});
