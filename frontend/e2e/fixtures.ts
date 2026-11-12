import { test as base } from '@playwright/test';
export { expect } from '@playwright/test';
export type { Page } from '@playwright/test';

// Public UI fixtures start with a healthy anonymous session. Auth tests override
// these routes explicitly; no browser suite contacts a real auth backend.
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route('**/api/v1/auth/csrf/', (route) =>
      route.fulfill({ json: { csrf_token: 'browser-bootstrap' } }),
    );
    await page.route('**/api/v1/auth/session/', (route) =>
      route.fulfill({ json: { authenticated: false, user: null } }),
    );
    await use(page);
  },
});
