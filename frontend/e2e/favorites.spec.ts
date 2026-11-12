import { expect, test, type Page } from './fixtures.js';
import { favorites } from '../tests/fixtures/favorites.js';
import { profile, seasonHistory } from '../tests/fixtures/profile.js';
import type { SessionUser } from '../src/api/index.js';

async function intercept(page: Page, initial: SessionUser | null = { id: 1, username: 'First' }) {
  const server = { user: initial };
  const reads: URL[] = [];
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
  await page.route('**/api/v1/me/favorites/?*', (route) => {
    const url = new URL(route.request().url());
    reads.push(url);
    if (!server.user)
      return route.fulfill({
        status: 403,
        json: { error: { code: 'authentication_required', message: 'Sign in.' } },
      });
    return route.fulfill({
      json: favorites(url.searchParams, server.user.username, {
        count: 101,
        next: url.searchParams.get('page') === '2' ? null : 'https://not-followed.example/next',
        previous: url.searchParams.get('page') === '2' ? '/ignored' : null,
      }),
    });
  });
  await page.route(/\/api\/v1\/players\/skater\/\d+\/\?/, (route) =>
    route.fulfill({ json: profile(new URL(route.request().url()).searchParams) }),
  );
  await page.route(/\/api\/v1\/players\/skater\/\d+\/seasons\/\?/, (route) =>
    route.fulfill({ json: seasonHistory(new URL(route.request().url()).searchParams) }),
  );
  return { server, reads };
}
async function signIn(page: Page, username = 'First') {
  await page.getByRole('link', { name: 'Sign in to view Favorites', exact: true }).click();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill('synthetic-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

test('gates anonymous private reads, preserves sign-in/profile return state and purges on logout', async ({
  page,
}) => {
  const { reads } = await intercept(page, null);
  const context = '/favorites?season_id=20262027&mode=averages&page=2';
  await page.goto(context);
  await expect(
    page.getByText('Sign in to view your saved Favorites.', { exact: true }),
  ).toBeVisible();
  expect(reads).toHaveLength(0);
  await signIn(page);
  await expect(page).toHaveURL(context);
  await expect(page.getByRole('link', { name: 'First Saved Player', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'First Saved Player', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Profile Skater');
  await page.reload();
  await page.getByRole('link', { name: 'Back to Favorites', exact: true }).click();
  await expect(page).toHaveURL(context);
  await expect(page.getByRole('link', { name: 'First Missing Player', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(
    page.getByText('Sign in to view your saved Favorites.', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('tbody')).toHaveCount(0);
  await expect(page.getByLabel('Favorites quota', { exact: true })).toHaveCount(0);
  const storage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
      state: history.state,
    }),
  );
  expect(storage).not.toContain('First Saved Player');
});

test('retains private missing/zero-season members and unfiltered quotas through filters, ordering and pagination', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/favorites?season_id=20262027');
  await expect(page.getByRole('link', { name: 'First Missing Player', exact: true })).toBeVisible();
  const zero = page
    .getByRole('row')
    .filter({ has: page.getByRole('rowheader', { name: 'First Zero Player', exact: true }) });
  expect((await zero.getByRole('cell').allTextContents())[4]).toBe('0');
  await expect(page.getByLabel('Favorites quota', { exact: true })).toContainText('5 of 100');
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
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.reload();
  await expect(page.getByLabel('Favorites quota', { exact: true })).toContainText('5 of 100');
  await page.goBack();
  await expect(page).not.toHaveURL(/page=2/);
  await page.getByLabel('Season ID (empty for latest loaded)', { exact: true }).fill('20272028');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(page.getByRole('heading', { level: 2 })).toContainText('2027–28');
  await expect(page.getByRole('link', { name: 'First Saved Player', exact: true })).toBeVisible();
  const row = page.locator('tbody tr').first();
  expect(
    (await row.getByRole('cell').allTextContents()).slice(4).every((value) => value === '—'),
  ).toBe(true);
  const width = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
  await expect(
    page.getByRole('region', { name: 'Favorite season statistics', exact: true }),
  ).toHaveAttribute('tabindex', '0');
});

test('handles expired authorization by an explicit session check without private-read loops', async ({
  page,
}) => {
  const { server } = await intercept(page);
  let reads = 0;
  await page.route('**/api/v1/me/favorites/?*', (route) => {
    reads += 1;
    return route.fulfill({
      status: 403,
      json: { error: { code: 'authentication_required', message: 'private authorization detail' } },
    });
  });
  await page.goto('/favorites?season_id=20262027');
  await expect(page.getByRole('alert')).toContainText('Access to Favorites could not be confirmed');
  expect(reads).toBe(1);
  await expect(page.getByText('private authorization detail')).toHaveCount(0);
  server.user = null;
  await page.getByRole('button', { name: 'Check session', exact: true }).click();
  await expect(
    page.getByText('Sign in to view your saved Favorites.', { exact: true }),
  ).toBeVisible();
  expect(reads).toBe(1);
  await expect(page.locator('tbody')).toHaveCount(0);
});

test('does not restore a first-account response after logout and sign-in as another account', async ({
  page,
}) => {
  const { server } = await intercept(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let oldStarted = false;
  await page.route('**/api/v1/me/favorites/?*', async (route) => {
    const query = new URL(route.request().url()).searchParams;
    if (server.user?.id === 1) {
      oldStarted = true;
      const old = favorites(query, 'First');
      await gate;
      await route.fulfill({ json: old }).catch(() => undefined);
      return;
    }
    return route.fulfill({ json: favorites(query, 'Second') });
  });
  await page.goto('/favorites?season_id=20262027');
  await expect.poll(() => oldStarted).toBe(true);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(
    page.getByText('Sign in to view your saved Favorites.', { exact: true }),
  ).toBeVisible();
  await signIn(page, 'Second');
  await expect(page.getByRole('link', { name: 'Second Saved Player', exact: true })).toBeVisible();
  release();
  await expect(page.getByRole('link', { name: 'First Saved Player', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Second Saved Player', exact: true })).toBeVisible();
});

test('recovers private page failures and switches goalie contracts without borrowing public data', async ({
  page,
}) => {
  await intercept(page);
  let fail = true;
  await page.route('**/api/v1/me/favorites/?*', (route) =>
    fail
      ? route.fulfill({ status: 503, contentType: 'text/html', body: 'private gateway detail' })
      : route.fulfill({ json: favorites(new URL(route.request().url()).searchParams) }),
  );
  await page.goto('/favorites?season_id=20262027&mode=averages&goals_min=0.5');
  await expect(page.getByRole('alert')).toContainText('Unable to load saved Favorites');
  await expect(page.getByText('private gateway detail')).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('link', { name: 'First Saved Player', exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Player type', exact: true }).selectOption('goalie');
  await page.getByRole('button', { name: 'Apply selections', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Favorite season statistics', exact: true }),
  ).toContainText('91.5%');
  expect(new URL(page.url()).searchParams.has('goals_min')).toBe(false);
  expect(new URL(page.url()).searchParams.get('mode')).toBe('totals');
});
