import { expect, test, type Page } from './fixtures.js';
import type { SessionUser } from '../src/api/index.js';
import { gameDates, games } from '../tests/fixtures/scoreboard.js';

async function authServer(page: Page) {
  const state = {
    user: null as SessionUser | null,
    token: 'bootstrap-token',
    csrfFail: false,
    loseLogin: false,
    loseLogout: false,
    discoveryDown: false,
  };
  const posts: Array<{
    path: string;
    body: unknown;
    token: string | undefined;
    cookie: string | undefined;
  }> = [];
  await page.route('**/api/v1/auth/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/csrf/'))
      return route.fulfill({
        json: { csrf_token: state.token },
        headers: { 'Set-Cookie': 'csrf_state=opaque; HttpOnly; Path=/; SameSite=Lax' },
      });
    if (path.endsWith('/session/'))
      return state.discoveryDown
        ? route.fulfill({
            status: 502,
            contentType: 'text/html',
            body: '<h1>private gateway detail</h1>',
          })
        : route.fulfill({ json: { authenticated: !!state.user, user: state.user } });
    const headers = await request.allHeaders();
    const body = request.postData() ? request.postDataJSON() : null;
    posts.push({ path, body, token: headers['x-csrftoken'], cookie: headers['cookie'] });
    if (state.csrfFail) {
      state.token = 'external-rotation';
      return route.fulfill({
        status: 403,
        json: { error: { code: 'csrf_failed', message: 'CSRF failed.' } },
      });
    }
    if (headers['x-csrftoken'] !== state.token)
      return route.fulfill({
        status: 403,
        json: { error: { code: 'csrf_failed', message: 'Bad token.' } },
      });
    if (path.endsWith('/login/')) {
      if (body.password === 'wrong')
        return route.fulfill({
          status: 400,
          json: { error: { code: 'invalid_credentials', message: 'Invalid credentials.' } },
        });
      state.user = { id: 1, username: body.username };
      state.token = 'login-token';
      if (state.loseLogin) return route.abort('failed');
    } else {
      state.user = null;
      state.token = 'logout-token';
      if (state.loseLogout) return route.abort('failed');
    }
    return route.fulfill({
      json: { authenticated: !!state.user, user: state.user, csrf_token: state.token },
      headers: { 'Set-Cookie': 'sessionid=opaque-session; HttpOnly; Path=/; SameSite=Lax' },
    });
  });
  return { state, posts };
}
async function fillLogin(page: Page, password = '  exact password  ') {
  await page.getByLabel('Username', { exact: true }).fill('first');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

test('uses HttpOnly-compatible CSRF, returns to the original scoreboard and signs out with a rotated token', async ({
  page,
}) => {
  const { posts } = await authServer(page);
  await page.route('**/api/v1/games/dates/**', (route) => route.fulfill({ json: gameDates() }));
  await page.route(/\/api\/v1\/games\/\?/, (route) => route.fulfill({ json: games() }));
  await page.goto('/games?date=2026-11-12&page=2');
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveTitle('Sign in | NHL Statso Maniacs');
  await fillLogin(page);
  await expect(page).toHaveURL('/games?date=2026-11-12&page=2');
  const header = page.getByRole('region', { name: 'Sign-in status', exact: true });
  await expect(header).toContainText('Signed in as first');
  expect(posts[0]!.body).toEqual({ username: 'first', password: '  exact password  ' });
  expect(posts[0]!.token).toBe('bootstrap-token');
  expect(posts[0]!.cookie).toContain('csrf_state=opaque');
  expect(await page.evaluate(() => document.cookie)).not.toContain('csrf_state');
  expect(await page.evaluate(() => document.cookie)).not.toContain('sessionid');
  await header.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(header.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible();
  expect(posts).toHaveLength(2);
  expect(posts[1]!.path).toBe('/api/v1/auth/logout/');
  expect(posts[1]!.token).toBe('login-token');
  await expect(page).toHaveURL('/games?date=2026-11-12&page=2');
});

test('shows generic credential failure, clears the password and rejects an external return target', async ({
  page,
}) => {
  await authServer(page);
  await page.goto('/login?returnTo=https%3A%2F%2Fexample.com');
  await fillLogin(page, 'wrong');
  await expect(page.getByRole('alert')).toContainText('Unable to sign in with those credentials.');
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Username', { exact: true })).toHaveValue('first');
  const loginSize = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(loginSize.width).toBeLessThanOrEqual(loginSize.viewport);
  await fillLogin(page, 'correct');
  await expect(page).toHaveURL('/');
  const size = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(size.width).toBeLessThanOrEqual(size.viewport);
});

test('rechecks a CSRF rejection without replaying login and accepts a later explicit submit', async ({
  page,
}) => {
  const { state, posts } = await authServer(page);
  await page.goto('/login');
  state.csrfFail = true;
  await fillLogin(page);
  await expect(page.getByRole('alert')).toContainText('Your session changed.');
  expect(posts).toHaveLength(1);
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
  state.csrfFail = false;
  await fillLogin(page);
  await expect(page).toHaveURL('/');
  expect(posts).toHaveLength(2);
  expect(posts[1]!.token).toBe('external-rotation');
});

test('reconciles lost login/logout responses without repeating either POST', async ({ page }) => {
  const { state, posts } = await authServer(page);
  await page.goto('/login');
  state.loseLogin = true;
  await fillLogin(page);
  await expect(page.getByRole('alert')).toContainText('The request could not be confirmed.');
  await expect(page.getByRole('region', { name: 'Sign-in status', exact: true })).toContainText(
    'Signed in as first',
  );
  expect(posts).toHaveLength(1);
  await page.getByRole('link', { name: 'Continue', exact: true }).click();
  await expect(page).toHaveURL('/');
  state.loseLogout = true;
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  const header = page.getByRole('region', { name: 'Sign-in status', exact: true });
  await expect(header.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(header).toContainText('The request could not be confirmed.');
  expect(posts).toHaveLength(2);
});

test('distinguishes unavailable discovery from anonymous state and handles session expiry on reload', async ({
  page,
}) => {
  const { state, posts } = await authServer(page);
  state.discoveryDown = true;
  await page.goto('/');
  const header = page.getByRole('region', { name: 'Sign-in status', exact: true });
  await expect(header).toContainText('Sign-in status unavailable.');
  await expect(header.getByRole('link', { name: 'Sign in', exact: true })).toHaveCount(0);
  await expect(page.getByText('private gateway detail')).toHaveCount(0);
  state.discoveryDown = false;
  state.user = { id: 1, username: 'first' };
  await header.getByRole('button', { name: 'Check session', exact: true }).click();
  await expect(header).toContainText('Signed in as first');
  state.user = null;
  await page.reload();
  await expect(header.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible();
  expect(posts).toHaveLength(0);
});
