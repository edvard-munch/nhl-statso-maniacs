import { expect, test, type Page } from './fixtures.js';

const LINK = { uidb64: 'c2Vuc2l0aXZlLWlk', token: 'fake-reset-secret-123' };
const PASSWORD = '  exact new password  ';
const linkUrl = (link = LINK) => `/recover-password/#${new URLSearchParams(link)}`;
async function fillPasswords(page: Page, confirmation = PASSWORD) {
  await page.getByLabel('New password', { exact: true }).fill(PASSWORD);
  await page.getByLabel('Confirm new password', { exact: true }).fill(confirmation);
  await page.getByRole('button', { name: 'Set new password', exact: true }).click();
}
async function assertScrubbed(page: Page, secrets = [LINK.uidb64, LINK.token]) {
  await expect(page).toHaveURL('/recover-password/');
  const navigation = await page.evaluate(() =>
    JSON.stringify({
      url: location.href,
      state: history.state,
      links: Array.from(document.querySelectorAll('a'), (link) => link.href),
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  for (const secret of secrets) expect(navigation).not.toContain(secret);
}

test('requests reset instructions with a generic acknowledgement for different email addresses', async ({
  page,
}) => {
  const emails: string[] = [];
  await page.route('**/api/v1/auth/password-reset/', (route) => {
    emails.push(route.request().postDataJSON().email);
    return route.fulfill({ json: { accepted: true } });
  });
  await page.goto('/login');
  await page.getByRole('link', { name: 'Forgot password?', exact: true }).click();
  for (const email of ['known@example.invalid', 'unknown@example.invalid']) {
    await page.getByLabel('Email', { exact: true }).fill(email);
    await page.getByRole('button', { name: 'Send reset instructions', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'Request received', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText('does not confirm an account exists or that email was delivered', {
        exact: false,
      }),
    ).toBeVisible();
    await expect(page.getByText(email, { exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Send another request', exact: true }).click();
  }
  expect(emails).toEqual(['known@example.invalid', 'unknown@example.invalid']);
  expect(page.url()).not.toContain('example.invalid');
});

test('handles unavailable/lost mail requests without claiming delivery or automatically resending', async ({
  page,
}) => {
  let requests = 0;
  await page.route('**/api/v1/auth/password-reset/', (route) => {
    requests += 1;
    return requests === 1
      ? route.fulfill({
          status: 503,
          json: { error: { code: 'password_reset_unavailable', message: 'Unavailable.' } },
        })
      : route.abort('failed');
  });
  await page.goto('/password-reset');
  await page.getByLabel('Email', { exact: true }).fill('any@example.invalid');
  await page.getByRole('button', { name: 'Send reset instructions', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('currently unavailable');
  expect(requests).toBe(1);
  await page.getByRole('button', { name: 'Send reset instructions', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('The request could not be confirmed');
  await expect(page.getByRole('heading', { name: 'Request received', exact: true })).toHaveCount(0);
  expect(requests).toBe(2);
});

test('scrubs the email fragment, preserves exact password values and requires explicit sign-in after reset', async ({
  page,
}) => {
  let validations = 0;
  let confirmations = 0;
  let authenticated = true;
  let csrf = 'before-reset';
  const urls: string[] = [];
  page.on('request', (request) => urls.push(request.url()));
  await page.route('**/api/v1/auth/csrf/', (route) =>
    route.fulfill({ json: { csrf_token: csrf } }),
  );
  await page.route('**/api/v1/auth/session/', (route) =>
    route.fulfill({
      json: { authenticated, user: authenticated ? { id: 7, username: 'target' } : null },
    }),
  );
  await page.route('**/api/v1/auth/password-reset/validate/', (route) => {
    validations += 1;
    expect(route.request().postDataJSON()).toEqual(LINK);
    return route.fulfill({ json: { valid: true } });
  });
  await page.route('**/api/v1/auth/password-reset/confirm/', (route) => {
    confirmations += 1;
    const body = route.request().postDataJSON();
    expect(body.uidb64).toBe(LINK.uidb64);
    expect(body.token).toBe(LINK.token);
    expect(body.new_password1).toBe(PASSWORD);
    if (confirmations === 1)
      return route.fulfill({
        status: 400,
        json: {
          error: {
            code: 'invalid_parameters',
            message: 'Invalid.',
            fields: { new_password2: ['Passwords do not match.'] },
          },
        },
      });
    expect(body.new_password2).toBe(PASSWORD);
    authenticated = false;
    csrf = 'after-reset';
    return route.fulfill({ json: { password_reset: true, login_required: true } });
  });
  await page.goto(linkUrl());
  await expect(page.getByLabel('New password', { exact: true })).toBeVisible();
  await assertScrubbed(page);
  await fillPasswords(page, 'different');
  await expect(page.getByText('Passwords do not match.', { exact: true })).toBeVisible();
  await expect(page.getByLabel('New password', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Confirm new password', { exact: true })).toHaveValue('');
  await fillPasswords(page);
  await expect(page.getByRole('heading', { name: 'Password changed', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Sign-in status', exact: true })).not.toContainText(
    'Signed in as target',
  );
  expect(validations).toBe(1);
  expect(confirmations).toBe(2);
  expect(urls.some((url) => url.includes(LINK.uidb64) || url.includes(LINK.token))).toBe(false);
  expect(urls.some((url) => url.includes('/auth/login/'))).toBe(false);
  await assertScrubbed(page);
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('invalid or no longer available');
  expect(validations).toBe(1);
  expect(confirmations).toBe(2);
});

test('rejects an expired/used link generically without showing account or secret values', async ({
  page,
}) => {
  let confirmations = 0;
  await page.route('**/api/v1/auth/password-reset/validate/', (route) =>
    route.fulfill({
      status: 400,
      json: { error: { code: 'invalid_reset_token', message: 'Invalid.' } },
    }),
  );
  await page.route('**/api/v1/auth/password-reset/confirm/', (route) => {
    confirmations += 1;
    return route.abort();
  });
  await page.goto(linkUrl());
  await expect(page.getByRole('alert')).toContainText('invalid or no longer available');
  await expect(page.getByLabel('New password', { exact: true })).toHaveCount(0);
  await assertScrubbed(page);
  expect(await page.locator('body').innerText()).not.toContain(LINK.token);
  expect(confirmations).toBe(0);
});

test('does not replay an uncertain password change or infer success from a subsequently invalid link', async ({
  page,
}) => {
  let confirmations = 0;
  await page.route('**/api/v1/auth/password-reset/validate/', (route) =>
    confirmations
      ? route.fulfill({
          status: 400,
          json: { error: { code: 'invalid_reset_token', message: 'Invalid.' } },
        })
      : route.fulfill({ json: { valid: true } }),
  );
  await page.route('**/api/v1/auth/password-reset/confirm/', (route) => {
    confirmations += 1;
    return route.abort('failed');
  });
  await page.goto(linkUrl());
  await fillPasswords(page);
  await expect(page.getByRole('alert')).toContainText('Password change could not be confirmed');
  await expect(page.getByRole('heading', { name: 'Password changed', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('New password', { exact: true })).toHaveCount(0);
  expect(confirmations).toBe(1);
  await page.getByRole('button', { name: 'Check link again', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('invalid or no longer available');
  expect(confirmations).toBe(1);
});

test('scrubs a second reset fragment opened in the same document and revalidates its own link', async ({
  page,
}) => {
  const tokens: string[] = [];
  await page.route('**/api/v1/auth/password-reset/validate/', (route) => {
    tokens.push(route.request().postDataJSON().token);
    return route.fulfill({ json: { valid: true } });
  });
  await page.goto(linkUrl());
  await expect(page.getByLabel('New password', { exact: true })).toBeVisible();
  const second = { uidb64: 'c2Vjb25kLWlk', token: 'second-reset-secret' };
  await page.evaluate((hash) => {
    location.hash = hash;
  }, new URLSearchParams(second).toString());
  await expect.poll(() => tokens).toEqual([LINK.token, second.token]);
  await expect(page.getByLabel('New password', { exact: true })).toBeVisible();
  await assertScrubbed(page, [LINK.uidb64, LINK.token, second.uidb64, second.token]);
});
