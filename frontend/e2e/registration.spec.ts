import { expect, test, type Page } from './fixtures.js';
import { registration } from '../tests/fixtures/registration.js';
import { gameDates, games } from '../tests/fixtures/scoreboard.js';

async function fill(page: Page, overrides: Partial<ReturnType<typeof registration>> = {}) {
  const values = registration(overrides);
  await page.getByLabel('Username', { exact: true }).fill(values.username);
  await page.getByLabel('Email', { exact: true }).fill(values.email);
  await page.getByLabel('Password', { exact: true }).fill(values.password1);
  await page.getByLabel('Confirm password', { exact: true }).fill(values.password2);
}
const success = { user: { id: 42, username: 'new-user' }, login_required: true };

test('creates anonymously without signing in, then requires an explicit sign-in and preserves the original games URL', async ({
  page,
}) => {
  let registrations = 0;
  let logins = 0;
  await page.route('**/api/v1/games/dates/**', (route) => route.fulfill({ json: gameDates() }));
  await page.route(/\/api\/v1\/games\/\?/, (route) => route.fulfill({ json: games() }));
  await page.route('**/api/v1/auth/register/', (route) => {
    registrations += 1;
    expect(route.request().postDataJSON()).toEqual(registration());
    expect(route.request().headers()['x-csrftoken']).toBe('browser-bootstrap');
    return route.fulfill({ status: 201, json: success });
  });
  await page.route('**/api/v1/auth/login/', (route) => {
    logins += 1;
    expect(route.request().headers()['x-csrftoken']).toBe('browser-bootstrap');
    return route.fulfill({
      json: { authenticated: true, user: success.user, csrf_token: 'after-login' },
    });
  });
  await page.goto('/games?date=2026-11-12&page=2');
  await page.getByRole('link', { name: 'Create account', exact: true }).click();
  await expect(page).toHaveTitle('Create account | NHL Statso Maniacs');
  await fill(page);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account created', exact: true })).toBeVisible();
  await expect(
    page.getByText('You have not been signed in to the new account.', { exact: false }),
  ).toBeVisible();
  expect(registrations).toBe(1);
  expect(logins).toBe(0);
  await expect(page.getByRole('region', { name: 'Sign-in status', exact: true })).not.toContainText(
    'Signed in as new-user',
  );
  await page.getByRole('link', { name: 'Sign in to the new account', exact: true }).click();
  await page.getByLabel('Username', { exact: true }).fill('new-user');
  await page.getByLabel('Password', { exact: true }).fill(registration().password1);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL('/games?date=2026-11-12&page=2');
  await expect(page.getByRole('region', { name: 'Sign-in status', exact: true })).toContainText(
    'Signed in as new-user',
  );
  expect(logins).toBe(1);
});

test('shows server field errors, clears passwords, retains correctable fields and recovers on explicit submit', async ({
  page,
}) => {
  let requests = 0;
  await page.route('**/api/v1/auth/register/', (route) => {
    requests += 1;
    return requests === 1
      ? route.fulfill({
          status: 400,
          json: {
            error: {
              code: 'invalid_parameters',
              message: 'Invalid.',
              fields: {
                username: ['Already exists.'],
                email: ['Enter a valid email address.'],
                password2: ['Passwords do not match.'],
              },
            },
          },
        })
      : route.fulfill({ status: 201, json: success });
  });
  await page.goto('/login');
  await page.getByRole('link', { name: 'Create account', exact: true }).click();
  await fill(page, { username: 'taken', email: 'name@invalid', password2: 'different' });
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByText('Already exists.', { exact: true })).toBeVisible();
  await expect(page.getByText('Passwords do not match.', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue('name@invalid');
  await expect(page.getByLabel('Username', { exact: true })).toHaveValue('taken');
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Confirm password', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Confirm password', { exact: true })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  const size = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(size.width).toBeLessThanOrEqual(size.viewport);
  await fill(page);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account created', exact: true })).toBeVisible();
  expect(requests).toBe(2);
});

test('preserves the existing signed-in caller when another account is created', async ({
  page,
}) => {
  let loginRequests = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/auth/login/') loginRequests += 1;
  });
  await page.route('**/api/v1/auth/session/', (route) =>
    route.fulfill({ json: { authenticated: true, user: { id: 7, username: 'existing' } } }),
  );
  const longUsername = 'n'.repeat(144);
  await page.route('**/api/v1/auth/register/', (route) =>
    route.fulfill({
      status: 201,
      json: { ...success, user: { ...success.user, username: longUsername } },
    }),
  );
  await page.goto('/register');
  const header = page.getByRole('region', { name: 'Sign-in status', exact: true });
  await expect(header).toContainText('Signed in as existing');
  await fill(page, { username: longUsername });
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account created', exact: true })).toBeVisible();
  await expect(header).toContainText('Signed in as existing');
  await expect(
    page.getByText('You are still signed in as existing.', { exact: true }),
  ).toBeVisible();
  expect(loginRequests).toBe(0);
  const size = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(size.width).toBeLessThanOrEqual(size.viewport);
});

test('recovers CSRF read-only and waits for another explicit registration submit', async ({
  page,
}) => {
  let requests = 0;
  let token = 'first-token';
  await page.route('**/api/v1/auth/csrf/', (route) =>
    route.fulfill({ json: { csrf_token: token } }),
  );
  await page.route('**/api/v1/auth/register/', (route) => {
    requests += 1;
    if (requests === 1) {
      token = 'changed-token';
      return route.fulfill({
        status: 403,
        json: { error: { code: 'csrf_failed', message: 'CSRF failed.' } },
      });
    }
    expect(route.request().headers()['x-csrftoken']).toBe('changed-token');
    return route.fulfill({ status: 201, json: success });
  });
  await page.goto('/register');
  await fill(page);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Your session changed.');
  expect(requests).toBe(1);
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Confirm password', { exact: true })).toHaveValue('');
  await fill(page);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account created', exact: true })).toBeVisible();
  expect(requests).toBe(2);
});

test('treats a lost creation response as uncertain and never resubmits or assumes sign-in', async ({
  page,
}) => {
  let requests = 0;
  await page.route('**/api/v1/auth/register/', (route) => {
    requests += 1;
    return route.abort('failed');
  });
  await page.goto('/register');
  await fill(page);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Account creation could not be confirmed.');
  await expect(page.getByRole('heading', { name: 'Account created', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Confirm password', { exact: true })).toHaveValue('');
  expect(requests).toBe(1);
  await expect(
    page.getByRole('link', { name: 'Already have an account? Sign in', exact: true }),
  ).toBeVisible();
});
