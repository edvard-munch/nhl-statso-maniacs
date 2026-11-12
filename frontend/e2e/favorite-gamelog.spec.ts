import { expect, test, type Page } from './fixtures.js';
import type { SessionUser } from '../src/api/index.js';
import { favoriteGamelog } from '../tests/fixtures/favorite-gamelog.js';
import { favorites } from '../tests/fixtures/favorites.js';
import { profile, seasonHistory } from '../tests/fixtures/profile.js';
import { gamelogGameDetail } from '../tests/fixtures/gamelog.js';
async function intercept(page: Page, user: SessionUser | null = { id: 1, username: 'First' }) {
  const server = {
    user,
    fail: false,
    deny: false,
    delay: false,
    started: false,
    release: () => {},
    reads: [] as URL[],
  };
  await page.route('**/api/v1/auth/session/', (route) =>
    route.fulfill({ json: { authenticated: !!server.user, user: server.user } }),
  );
  await page.route('**/api/v1/auth/login/', (route) => {
    const body = route.request().postDataJSON();
    server.user = { id: body.username === 'Second' ? 2 : 1, username: body.username };
    return route.fulfill({
      json: { authenticated: true, user: server.user, csrf_token: 'login-token' },
    });
  });
  await page.route('**/api/v1/auth/logout/', (route) => {
    server.user = null;
    return route.fulfill({
      json: { authenticated: false, user: null, csrf_token: 'logout-token' },
    });
  });
  await page.route('**/api/v1/me/favorites/?*', (route) =>
    route.fulfill({
      json: favorites(new URL(route.request().url()).searchParams, server.user?.username),
    }),
  );
  await page.route('**/api/v1/me/favorites/gamelog/?*', async (route) => {
    const url = new URL(route.request().url());
    server.reads.push(url);
    if (server.deny || !server.user)
      return route.fulfill({
        status: 403,
        json: {
          error: { code: 'authentication_required', message: 'private authorization detail' },
        },
      });
    if (server.fail)
      return route.fulfill({
        status: 503,
        contentType: 'text/html',
        body: 'private gateway detail',
      });
    const data = favoriteGamelog(url.searchParams, server.user.username);
    const ordered = url.searchParams.get('ordering')?.startsWith('-player_name')
      ? [data.results[1], data.results[0], data.results[2], data.results[3]]
      : data.results;
    const response = {
      ...data,
      count: url.searchParams.get('season_id') === '20272028' ? 0 : 250,
      results: url.searchParams.get('season_id') === '20272028' ? [] : ordered,
      next: url.searchParams.get('page') === '2' ? null : '/ignored',
      previous: url.searchParams.get('page') === '2' ? '/ignored' : null,
      meta: {
        ...data.meta,
        quota:
          server.user.id === 2
            ? {
                limit: 100,
                skaters_count: 2,
                goalies_count: 0,
                total_count: 2,
                remaining: 98,
                over_limit: false,
              }
            : data.meta.quota,
      },
    };
    if (server.delay && server.user.id === 1) {
      server.started = true;
      await new Promise<void>((resolve) => {
        server.release = resolve;
      });
      await route.fulfill({ json: response }).catch(() => undefined);
      return;
    }
    return route.fulfill({ json: response });
  });
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/\?/, (route) => {
    const url = new URL(route.request().url());
    url.searchParams.set('player_type', url.pathname.includes('/goalie/') ? 'goalie' : 'skater');
    return route.fulfill({ json: profile(url.searchParams) });
  });
  await page.route(/\/api\/v1\/players\/(skater|goalie)\/\d+\/seasons\/\?/, (route) =>
    route.fulfill({ json: seasonHistory(new URL(route.request().url()).searchParams) }),
  );
  await page.route('**/api/v1/games/2026020001/', (route) =>
    route.fulfill({ json: gamelogGameDetail() }),
  );
  return server;
}
async function login(page: Page, username = 'First') {
  await page.getByRole('link', { name: 'Sign in to view Favorites gamelog', exact: true }).click();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill('synthetic-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

test('gates anonymous reads and preserves private gamelog/profile/game/list context through reload', async ({
  page,
}) => {
  const server = await intercept(page, null);
  const direct = '/favorites/gamelog?ordering=player_name,-date&page=2';
  await page.goto(direct);
  await expect(
    page.getByText('Sign in to view your Favorites game log.', { exact: true }),
  ).toBeVisible();
  expect(server.reads).toHaveLength(0);
  await login(page);
  await expect(page).toHaveURL(direct);
  await expect(
    page.getByRole('link', { name: 'First Saved Player', exact: true }).first(),
  ).toBeVisible();
  const list = '/favorites?season_id=20262027&mode=averages&goals_min=0.5';
  await page.goto(list);
  await page.getByRole('link', { name: 'All saved Favorite games', exact: true }).click();
  await expect(page.getByRole('heading', { level: 2 })).toContainText(
    'All saved seasons and dates',
  );
  expect(new URL(page.url()).searchParams.has('mode')).toBe(false);
  expect(new URL(page.url()).searchParams.has('season_id')).toBe(false);
  const context = new URL(page.url()).pathname + new URL(page.url()).search;
  await page
    .getByRole('link', { name: '2026-11-12 · Game 2026020001', exact: true })
    .first()
    .click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Game details');
  await page.reload();
  await page.getByRole('link', { name: 'Back to Favorites gamelog', exact: true }).click();
  await expect(page).toHaveURL(context);
  await page.getByRole('link', { name: 'First Saved Player', exact: true }).first().click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater');
  await page.getByRole('link', { name: 'Back to Favorites gamelog', exact: true }).click();
  await expect(page).toHaveURL(context);
  await page.getByRole('link', { name: 'Back to Favorites', exact: true }).click();
  await expect(page).toHaveURL(list);
  expect(
    server.reads.every((url) => !url.searchParams.has('returnTo') && !url.searchParams.has('mode')),
  ).toBe(true);
});

test('retains per-player same-game rows, unknown evidence and named ordering/filter/page URL state', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/favorites/gamelog');
  await expect(
    page.getByRole('link', { name: '2026-11-12 · Game 2026020001', exact: true }),
  ).toHaveCount(2);
  const rows = page.locator('tbody tr');
  expect(await rows.first().getByRole('cell').allTextContents()).toEqual(
    expect.arrayContaining(['12:34', '00:00', '01:35']),
  );
  await expect(rows.nth(2)).toContainText('Unverified');
  await expect(rows.nth(2).getByRole('link')).toHaveCount(1);
  await expect(rows.nth(3)).toContainText('Date unavailable');
  await page.getByText('Game statistic filters', { exact: true }).click();
  await page.getByRole('spinbutton', { name: 'PP TOI (seconds) minimum', exact: true }).fill('0');
  await page
    .getByRole('combobox', { name: 'Hits availability', exact: true })
    .selectOption('false');
  await page
    .getByRole('searchbox', { name: 'Search favorite player name', exact: true })
    .fill('%_Name');
  await page.getByLabel('Ordering', { exact: true }).fill('-player_name,-date');
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(page).toHaveURL(/ordering=-player_name,-date/);
  await expect(page.locator('tbody tr').first().getByRole('link').first()).toHaveText(
    'First Second Player',
  );
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.reload();
  await expect(
    page.getByRole('searchbox', { name: 'Search favorite player name', exact: true }),
  ).toHaveValue('%_Name');
  await expect(page.getByText(/250 saved player-game rows/)).toBeVisible();
  expect(new URL(page.url()).searchParams.get('pp_toi_seconds_min')).toBe('0');
  expect(new URL(page.url()).searchParams.get('hits_isnull')).toBe('false');
  await page.goBack();
  await expect(page).not.toHaveURL(/page=2/);
  const width = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
  await expect(
    page.getByRole('region', { name: 'Favorites game statistics', exact: true }),
  ).toHaveAttribute('tabindex', '0');
});

test('purges accepted private rows and quota on logout and ignores late results after account switching', async ({
  page,
}) => {
  const server = await intercept(page);
  await page.goto('/favorites/gamelog');
  await expect(
    page.getByRole('link', { name: 'First Saved Player', exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByLabel('Favorites gamelog quota', { exact: true })).toContainText(
    '5 of 100',
  );
  server.delay = true;
  await page.getByRole('button', { name: 'Refresh gamelog', exact: true }).click();
  await expect.poll(() => server.started).toBe(true);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(
    page.getByText('Sign in to view your Favorites game log.', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('tbody')).toHaveCount(0);
  await expect(page.getByLabel('Favorites gamelog quota', { exact: true })).toHaveCount(0);
  await login(page, 'Second');
  await expect(
    page.getByRole('link', { name: 'Second Saved Player', exact: true }).first(),
  ).toBeVisible();
  server.release();
  await expect(page.getByRole('link', { name: 'First Saved Player', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Favorites gamelog quota', { exact: true })).toContainText(
    '2 of 100',
  );
  const storage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
      history: history.state,
    }),
  );
  expect(storage).not.toContain('First Saved Player');
  expect(storage).not.toContain('Second Saved Player');
});

test('handles expired authorization with explicit checking and no automatic read loop', async ({
  page,
}) => {
  const server = await intercept(page);
  server.deny = true;
  await page.goto('/favorites/gamelog');
  await expect(page.getByRole('alert')).toContainText(
    'Access to the Favorites game log could not be confirmed',
  );
  expect(server.reads).toHaveLength(1);
  await expect(page.getByText('private authorization detail')).toHaveCount(0);
  server.user = null;
  await page.getByRole('button', { name: 'Check session', exact: true }).click();
  await expect(
    page.getByText('Sign in to view your Favorites game log.', { exact: true }),
  ).toBeVisible();
  expect(server.reads).toHaveLength(1);
});

test('recovers failed reads, retains an explicit empty season, and switches typed goalie fields', async ({
  page,
}) => {
  const server = await intercept(page);
  server.fail = true;
  await page.goto('/favorites/gamelog?season_id=20272028');
  await expect(page.getByRole('alert')).toContainText('Unable to load saved Favorites game rows');
  await expect(page.getByText('private gateway detail')).toHaveCount(0);
  server.fail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(
    page.getByText(
      'No Favorite game rows match this selection. Players without game rows remain in Favorites.',
      { exact: true },
    ),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.get('season_id')).toBe('20272028');
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(
    page.getByRole('link', { name: 'First Saved Player', exact: true }).first(),
  ).toBeVisible();
  await page.getByRole('combobox', { name: 'Player type', exact: true }).selectOption('goalie');
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Favorites game statistics', exact: true }),
  ).toContainText('90.6%');
  await expect(page.getByRole('button', { name: 'Sort by Goals', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Sort by Decision', exact: true })).toBeAttached();
});
