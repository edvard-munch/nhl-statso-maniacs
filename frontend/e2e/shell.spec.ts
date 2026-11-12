import { expect, test } from '@playwright/test';

test('built shell fits the viewport and keyboard users can skip navigation', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Follow NHL games and players');
  await expect(page).toHaveTitle('Home | NHL Statso Maniacs');
  await expect(
    page.getByRole('navigation').getByRole('link', { name: 'Home', exact: true }),
  ).toHaveAttribute('aria-current', 'page');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  const size = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(size.content).toBeLessThanOrEqual(size.viewport);
  expect(errors).toEqual([]);
});

test('deep links render a missing page and recover without a full navigation', async ({ page }) => {
  await page.goto('/missing/game');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found');
  await page.reload();
  await expect(page).toHaveTitle('Page not found | NHL Statso Maniacs');
  await page.evaluate(() => {
    Object.assign(window, { shellMarker: 'same-document' });
  });
  await page.getByRole('link', { name: 'Return home' }).click();
  await expect(page).toHaveURL('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Follow NHL games and players');
  await expect(page.getByRole('main')).toBeFocused();
  expect(await page.evaluate(() => Reflect.get(window, 'shellMarker'))).toBe('same-document');
});
