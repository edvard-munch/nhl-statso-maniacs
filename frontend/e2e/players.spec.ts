import { expect, test, type Page } from './fixtures.js';
import { catalogue, filterMetadata, loadedSeasons } from '../tests/fixtures/players.js';

async function intercept(page: Page) {
  await page.route('**/api/v1/seasons/?*', (route) => route.fulfill({ json: loadedSeasons }));
  await page.route('**/api/v1/players/filters/?*', (route) =>
    route.fulfill({ json: filterMetadata(new URL(route.request().url()).searchParams) }),
  );
  await page.route('**/api/v1/players/?*', (route) => {
    const query = new URL(route.request().url()).searchParams;
    return route.fulfill({
      json: catalogue(query, {
        count: 101,
        next: query.get('page') === '2' ? null : 'https://not-followed.example/next',
        previous: query.get('page') === '2' ? '/ignored' : null,
      }),
    });
  });
}

test('browses season statistics with full filter options, URL paging, sorting and history', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Browse players', exact: true }).click();
  await expect(page).toHaveURL('/players?season_id=20262027');
  await expect(page.getByRole('rowheader', { name: 'Season Skater' })).toBeVisible();
  await page.getByText('Filters and ranges', { exact: true }).click();
  await page.getByRole('checkbox', { name: 'Montreal Canadiens (MTL)', exact: true }).check();
  await page.getByRole('spinbutton', { name: 'Points minimum', exact: true }).fill('0');
  await page.getByRole('searchbox', { name: 'Search name', exact: true }).fill('Season');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(
    page.getByRole('checkbox', { name: 'Montreal Canadiens (MTL)', exact: true }),
  ).toBeChecked();
  expect(new URL(page.url()).searchParams.get('points_min')).toBe('0');
  await page.getByRole('button', { name: 'Sort by Points', exact: true }).click();
  await expect(page).toHaveURL(/ordering=-points/);
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.reload();
  await expect(page.getByRole('searchbox', { name: 'Search name', exact: true })).toHaveValue(
    'Season',
  );
  await expect(page.getByText(/Page 2\. Ordering: -points/)).toBeVisible();
  await page.goBack();
  await expect(page.getByText(/Page 1\. Ordering: -points/)).toBeVisible();
  await page.getByRole('combobox', { name: 'Season', exact: true }).selectOption('20252026');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(page.getByRole('heading', { level: 2 })).toContainText('2025–26');
  const size = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(size.content).toBeLessThanOrEqual(size.viewport);
  const table = page.getByRole('region', { name: 'Season player statistics', exact: true });
  await expect(table).toHaveAttribute('tabindex', '0');
});

test('switches averages and goalie contracts while preserving unknown and genuine zero values', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/players?season_id=20262027&mode=averages&points_min=0.2');
  await expect(page.getByRole('cell', { name: '0.375', exact: true })).toBeVisible();
  const cells = page.locator('tbody td');
  expect(await cells.allTextContents()).toContain('—');
  expect(await cells.allTextContents()).toContain('0');
  expect(await cells.allTextContents()).toContain('10:01');
  await page.getByRole('combobox', { name: 'Player type', exact: true }).selectOption('goalie');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(page.getByRole('rowheader', { name: 'Season Goalie', exact: true })).toBeVisible();
  expect(new URL(page.url()).searchParams.has('points_min')).toBe(false);
  await expect(page.getByRole('cell', { name: '91.5%', exact: true })).toBeAttached();
  await expect(page.getByRole('button', { name: 'Sort by Goals', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  expect(new URL(page.url()).searchParams.get('returnTo')).toContain('/players?');
});

test('keeps explicit empty seasons and recovers from errors without exposing stale rows or proxy details', async ({
  page,
}) => {
  await intercept(page);
  let fail = false;
  await page.route('**/api/v1/players/?*', (route) => {
    const query = new URL(route.request().url()).searchParams;
    if (fail)
      return route.fulfill({
        status: 503,
        contentType: 'text/html',
        body: '<h1>private proxy detail</h1>',
      });
    return route.fulfill({
      json: catalogue(
        query,
        query.get('season_id') === '20272028' ? { count: 0, results: [] } : {},
      ),
    });
  });
  await page.goto('/players?season_id=20272028');
  await expect(
    page.getByText('No saved players match this season and selection.', { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL('/players?season_id=20272028');
  await page.getByRole('combobox', { name: 'Season', exact: true }).selectOption('20262027');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(page.getByRole('rowheader', { name: 'Season Skater' })).toBeVisible();
  fail = true;
  await page.getByRole('button', { name: 'Sort by Points', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Unable to load saved players');
  await expect(page.getByRole('rowheader')).toHaveCount(0);
  await expect(page.getByText('private proxy detail')).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('rowheader', { name: 'Season Skater' })).toBeVisible();
});
