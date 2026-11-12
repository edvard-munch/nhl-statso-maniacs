import { expect, test, type Page } from './fixtures.js';
import { teams, teamDetail, teamPlayers } from '../tests/fixtures/teams.js';
import { profile, profileStats, seasonHistory } from '../tests/fixtures/profile.js';
async function intercept(page: Page) {
  await page.route('**/api/v1/teams/?*', (route) =>
    route.fulfill({
      json: teams(new URL(route.request().url()).searchParams, {
        count: 101,
        next: 'https://not-followed.example/next',
      }),
    }),
  );
  await page.route(/\/api\/v1\/teams\/\d+\/(?:\?.*)?$/, (route) =>
    route.fulfill({ json: teamDetail(new URL(route.request().url()).searchParams) }),
  );
  await page.route(/\/api\/v1\/teams\/\d+\/players\/\?/, (route) => {
    const query = new URL(route.request().url()).searchParams;
    return route.fulfill({
      json: teamPlayers(query, {
        count: 101,
        next: query.get('page') === '2' ? null : 'https://not-followed.example/next',
        previous: query.get('page') === '2' ? '/ignored' : null,
      }),
    });
  });
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/\?/, (route) => {
    const url = new URL(route.request().url());
    const query = url.searchParams;
    query.set('player_type', url.pathname.includes('/goalie/') ? 'goalie' : 'skater');
    return route.fulfill({
      json: profile(query, {
        selected_season: {
          availability: 'partial',
          stats: profileStats({ games: 10, goals: 4, assists: 4, points: 8 }),
        },
      }),
    });
  });
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/seasons\/\?/, (route) =>
    route.fulfill({ json: seasonHistory(new URL(route.request().url()).searchParams) }),
  );
}

test('browses saved identities and preserves directory/team context through profile navigation', async ({
  page,
}) => {
  await intercept(page);
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  await page.goto('/');
  await page.getByRole('link', { name: 'Browse teams', exact: true }).click();
  await expect(page.getByRole('rowheader', { name: 'Historical Team', exact: true })).toBeVisible();
  await page
    .getByRole('searchbox', { name: 'Search team name or abbreviation', exact: true })
    .fill('BUF');
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  const directory = new URL(page.url()).pathname + new URL(page.url()).search;
  await page.getByRole('link', { name: 'Buffalo Sabres', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Buffalo Sabres');
  await expect(page).toHaveURL(/season_id=20262027/);
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page.getByText(/Page 2\. Team season totals/)).toBeVisible();
  const table = page.getByRole('region', { name: 'Team season contributions', exact: true });
  expect(await table.locator('tbody tr').first().getByRole('cell').allTextContents()).toEqual(
    expect.arrayContaining(['6', '3', '18:31', '00:00', '—', '0']),
  );
  const context = new URL(page.url()).pathname + new URL(page.url()).search;
  await page.getByRole('link', { name: 'Traded Skater', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater');
  const selected = page
    .getByRole('region', { name: 'Selected season and career statistics', exact: true })
    .locator('tbody tr')
    .first();
  expect(await selected.getByRole('cell').allTextContents()).toEqual(
    expect.arrayContaining(['10', '4']),
  );
  await page.reload();
  await page.getByRole('link', { name: 'Back to team', exact: true }).click();
  await expect(page).toHaveURL(context);
  await page.getByRole('link', { name: 'Back to teams', exact: true }).click();
  await expect(page).toHaveURL(directory);
  expect(
    requests.some(
      (url) => url.includes('/players/filters/') || url.includes('not-followed.example'),
    ),
  ).toBe(false);
  const width = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
});

test('uses split averages and goalie contracts with filters, URL ordering and mobile scroll regions', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/teams/7?season_id=20262027&mode=averages&goals_min=0.5');
  const region = page.getByRole('region', { name: 'Team season contributions', exact: true });
  await expect(region).toContainText('0.5');
  await expect(region).toHaveAttribute('tabindex', '0');
  await page.getByText('Birth date and numeric filters', { exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Goals minimum', exact: true }).fill('0');
  await page
    .getByRole('combobox', { name: 'Hits availability', exact: true })
    .selectOption('false');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(page).toHaveURL(/goals_min=0/);
  expect(new URL(page.url()).searchParams.get('hits_isnull')).toBe('false');
  await page.getByRole('button', { name: 'Sort by Goals', exact: true }).click();
  await expect(page).toHaveURL(/ordering=-goals/);
  await page.reload();
  await expect(region).toContainText('0.5');
  await page.getByRole('combobox', { name: 'Player type', exact: true }).selectOption('goalie');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(region).toContainText('Split Goalie');
  await expect(region).toContainText('90.0%');
  expect(new URL(page.url()).searchParams.has('goals_min')).toBe(false);
  expect(new URL(page.url()).searchParams.get('mode')).toBe('totals');
  await expect(page.getByRole('button', { name: 'Sort by Goals', exact: true })).toHaveCount(0);
  const width = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  expect(new URL(page.url()).searchParams.get('returnTo')).toContain('/teams/7?');
});

test('retains explicit empty seasons and keeps team metadata during failed contribution-page recovery', async ({
  page,
}) => {
  await intercept(page);
  let fail = false;
  await page.route(/\/api\/v1\/teams\/\d+\/players\/\?/, (route) => {
    const query = new URL(route.request().url()).searchParams;
    if (fail)
      return route.fulfill({
        status: 404,
        json: { error: { code: 'not_found', message: 'private contribution detail', fields: {} } },
      });
    return route.fulfill({
      json: teamPlayers(
        query,
        query.get('season_id') === '20272028'
          ? { count: 0, results: [] }
          : { count: 101, next: '/ignored' },
      ),
    });
  });
  await page.goto('/teams/7?season_id=20272028');
  await expect(
    page.getByText('No saved team contributions match this season and selection.', { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL('/teams/7?season_id=20272028');
  await page.getByLabel('Season ID (empty for latest loaded)', { exact: true }).fill('20262027');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Traded Skater', exact: true })).toBeVisible();
  fail = true;
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Team metadata remains available');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Buffalo Sabres');
  await expect(page.getByText('private contribution detail')).toHaveCount(0);
  await expect(page.locator('tbody')).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'First page', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Traded Skater', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByText(/Page 2\. Team season totals/)).toBeVisible();
});

test('recovers directory errors and reloads applied conference/division/order filters', async ({
  page,
}) => {
  await intercept(page);
  let fail = true;
  await page.route('**/api/v1/teams/?*', (route) =>
    fail
      ? route.fulfill({ status: 503, contentType: 'text/html', body: 'private gateway detail' })
      : route.fulfill({ json: teams(new URL(route.request().url()).searchParams) }),
  );
  await page.goto('/teams?conference=Eastern&division=Atlantic&ordering=-name');
  await expect(page.getByRole('alert')).toContainText('Unable to load saved teams');
  await expect(page.getByText('private gateway detail')).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByLabel('Conferences (comma-separated)', { exact: true })).toHaveValue(
    'Eastern',
  );
  await page.reload();
  await expect(page.getByLabel('Divisions (comma-separated)', { exact: true })).toHaveValue(
    'Atlantic',
  );
  await expect(page.getByLabel('Ordering', { exact: true })).toHaveValue('-name');
});
