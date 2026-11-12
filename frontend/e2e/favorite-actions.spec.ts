import { expect, test, type Page } from './fixtures.js';
import { favorites } from '../tests/fixtures/favorites.js';
import { profile, seasonHistory } from '../tests/fixtures/profile.js';
async function intercept(page: Page) {
  const server = {
    members: new Set<string>(),
    token: 'write-csrf',
    mode: 'ok',
    writes: [] as { method: string; url: string; token: string | undefined; body: string | null }[],
    started: false,
    release: () => {},
  };
  const quota = () => ({
    limit: 100,
    skaters_count: [...server.members].filter((key) => key.startsWith('skater:')).length,
    goalies_count: [...server.members].filter((key) => key.startsWith('goalie:')).length,
    total_count: server.members.size,
    remaining: Math.max(0, 100 - server.members.size),
    over_limit: server.members.size > 100,
  });
  await page.route('**/api/v1/auth/csrf/', (route) =>
    route.fulfill({ json: { csrf_token: server.token } }),
  );
  await page.route('**/api/v1/auth/session/', (route) =>
    route.fulfill({ json: { authenticated: true, user: { id: 1, username: 'First' } } }),
  );
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/\?/, (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split('/');
    const id = Number(parts[parts.length - 2]);
    const data = profile(url.searchParams);
    return route.fulfill({
      json: {
        ...data,
        player: {
          ...data.player,
          nhl_id: id,
          name: id === 8480001 ? 'Profile Skater' : 'Other Skater',
        },
      },
    });
  });
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/seasons\/\?/, (route) =>
    route.fulfill({ json: seasonHistory(new URL(route.request().url()).searchParams) }),
  );
  await page.route('**/api/v1/me/favorites/?*', (route) => {
    const url = new URL(route.request().url());
    const data = favorites(url.searchParams);
    const type = url.searchParams.get('player_type') || 'skater';
    const base = data.results[0]!;
    const rows = [...server.members]
      .filter((key) => key.startsWith(`${type}:`))
      .sort()
      .map((key) => ({
        ...base,
        nhl_id: Number(key.split(':')[1]),
        player_type: type,
        name: key.endsWith('8480001') ? 'First Saved Player' : 'Other Saved Player',
      }));
    const current = Number(url.searchParams.get('page') || 1);
    const size = Number(url.searchParams.get('page_size') || 50);
    if (current > 1 && (current - 1) * size >= rows.length)
      return route.fulfill({
        status: 404,
        json: { error: { code: 'not_found', message: 'Missing page' } },
      });
    return route.fulfill({
      json: {
        ...data,
        results: rows.slice((current - 1) * size, current * size),
        count: rows.length,
        next: current * size < rows.length ? '/ignored' : null,
        previous: current > 1 ? '/ignored' : null,
        meta: { ...data.meta, quota: quota() },
      },
    });
  });
  await page.route(/\/api\/v1\/me\/favorites\/(skater|goalie)\/\d+\/$/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split('/');
    const type = parts[parts.length - 3]!;
    const id = Number(parts[parts.length - 2]);
    const key = `${type}:${id}`;
    server.writes.push({
      method: request.method(),
      url: request.url(),
      token: request.headers()['x-csrftoken'],
      body: request.postData(),
    });
    if (server.mode === 'csrf') {
      server.token = 'refreshed-csrf';
      return route.fulfill({
        status: 403,
        json: { error: { code: 'csrf_failed', message: 'private token detail' } },
      });
    }
    if (request.method() === 'PUT' && !server.members.has(key) && server.members.size >= 100)
      return route.fulfill({
        status: 409,
        json: { error: { code: 'favorites_quota_exceeded', message: 'Limit reached' } },
      });
    if (server.mode === 'hold') {
      server.started = true;
      await new Promise<void>((resolve) => {
        server.release = resolve;
      });
    }
    const existed = server.members.has(key);
    if (request.method() === 'DELETE') server.members.delete(key);
    else server.members.add(key);
    if (server.mode === 'lost') return route.abort('failed');
    if (request.method() === 'DELETE') return route.fulfill({ status: 204 });
    return route.fulfill({
      status: existed ? 200 : 201,
      json: { is_favorite: true, player_type: type, nhl_id: id, quota: quota() },
    });
  });
  return server;
}

test('saves explicitly, accepts idempotence at quota, and reports a new-player quota rejection', async ({
  page,
}) => {
  const server = await intercept(page);
  await page.goto('/players/skater/8480001?season_id=20262027');
  await page.getByRole('button', { name: 'Save Profile Skater to Favorites', exact: true }).click();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'was added',
  );
  expect(server.writes).toHaveLength(1);
  expect(server.writes[0]!.token).toBe('write-csrf');
  expect(server.writes[0]!.body).toBeNull();
  expect(new URL(server.writes[0]!.url).search).toBe('');
  for (let id = 1; id < 100; id++) server.members.add(`skater:${id}`);
  await page.getByRole('button', { name: 'Save Profile Skater to Favorites', exact: true }).click();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'already saved',
  );
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    '0 remaining',
  );
  await page.goto('/players/skater/8480002?season_id=20262027');
  await page.getByRole('button', { name: 'Save Other Skater to Favorites', exact: true }).click();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'Favorites limit',
  );
  expect(server.members.has('skater:8480002')).toBe(false);
  expect(server.writes).toHaveLength(3);
});

test('removes the last page row, preserves filters on first-page recovery, then reaches a true empty state', async ({
  page,
}) => {
  const server = await intercept(page);
  server.members.add('skater:8480001');
  server.members.add('skater:8480002');
  await page.goto('/favorites?season_id=20262027&page_size=1&page=2&search=Saved');
  await page
    .getByRole('button', { name: 'Remove Other Saved Player from Favorites', exact: true })
    .click();
  await expect(page).toHaveURL(/page=1/);
  expect(new URL(page.url()).searchParams.get('search')).toBe('Saved');
  await expect(page.getByRole('link', { name: 'First Saved Player', exact: true })).toBeVisible();
  await page
    .getByRole('button', { name: 'Remove First Saved Player from Favorites', exact: true })
    .click();
  await expect(page.getByText('No saved Favorites yet.', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Favorites quota', { exact: true })).toContainText('0 of 100');
  expect(server.writes.filter((write) => write.method === 'DELETE')).toHaveLength(2);
  await expect(page.locator('tbody')).toHaveCount(0);
});

test('checks membership after lost save and removal replies without automatically repeating either write', async ({
  page,
}) => {
  const server = await intercept(page);
  server.mode = 'lost';
  await page.goto('/players/skater/8480001?season_id=20262027');
  await page.getByRole('button', { name: 'Save Profile Skater to Favorites', exact: true }).click();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'currently saved',
  );
  expect(server.writes).toHaveLength(1);
  await page.goto('/favorites?season_id=20262027');
  await page
    .getByRole('button', { name: 'Remove First Saved Player from Favorites', exact: true })
    .click();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'currently absent',
  );
  await expect(page.getByText('No saved Favorites yet.', { exact: true })).toBeVisible();
  expect(server.writes).toHaveLength(2);
});

test('refreshes CSRF after rejection but waits for an explicit second save', async ({ page }) => {
  const server = await intercept(page);
  server.mode = 'csrf';
  await page.goto('/players/skater/8480001?season_id=20262027');
  await page.getByRole('button', { name: 'Save Profile Skater to Favorites', exact: true }).click();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'session changed',
  );
  await expect(page.getByText('private token detail')).toHaveCount(0);
  expect(server.writes).toHaveLength(1);
  expect(server.members.size).toBe(0);
  server.mode = 'ok';
  await page.getByRole('button', { name: 'Save Profile Skater to Favorites', exact: true }).click();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'was added',
  );
  expect(server.writes).toHaveLength(2);
  expect(server.writes[1]!.token).toBe('refreshed-csrf');
});

test('serializes pending writes with auth actions and keeps progress/results through view navigation', async ({
  page,
}) => {
  const server = await intercept(page);
  server.mode = 'hold';
  await page.goto('/players/skater/8480001?season_id=20262027');
  await page.getByRole('button', { name: 'Save Profile Skater to Favorites', exact: true }).click();
  await expect.poll(() => server.started).toBe(true);
  await expect(
    page.getByRole('button', { name: 'Save Profile Skater to Favorites', exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeDisabled();
  await page.getByRole('link', { name: 'Favorites', exact: true }).click();
  await expect(page.getByText('Waiting for session checks…', { exact: true })).toBeVisible();
  server.release();
  await expect(page.getByRole('link', { name: 'First Saved Player', exact: true })).toBeVisible();
  await expect(page.getByLabel('Favorites action result', { exact: true })).toContainText(
    'was added',
  );
  expect(server.writes).toHaveLength(1);
  const width = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
});
