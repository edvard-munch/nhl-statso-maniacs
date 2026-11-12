import { expect, test, type Page } from '@playwright/test';
import { gameDetail } from '../tests/fixtures/game-detail.js';
import { game, gameDates, games } from '../tests/fixtures/scoreboard.js';

async function clock(page: Page) {
  await page.clock.install({ time: new Date('2026-11-12T10:01:00Z') });
}

test('polls the selected scoreboard page without changing the date draft, focus or URL', async ({
  page,
}) => {
  await clock(page);
  let checks = 0;
  const queried: URL[] = [];
  await page.route('**/api/v1/games/dates/**', (route) => route.fulfill({ json: gameDates() }));
  await page.route(/\/api\/v1\/games\/\?/, (route) => {
    checks += 1;
    queried.push(new URL(route.request().url()));
    return route.fulfill({ json: games('2026-11-12', [game({ home_score: checks > 1 ? 4 : 2 })]) });
  });
  await page.goto('/games?date=2026-11-12&page=2');
  await expect(page.getByLabel('Home score: 2', { exact: true })).toBeVisible();
  const draft = page.getByLabel('Schedule date', { exact: true });
  await draft.fill('2026-11-14');
  await draft.focus();
  await page.clock.fastForward(60_000);
  await expect(page.getByLabel('Home score: 4', { exact: true })).toBeVisible();
  expect(queried).toHaveLength(2);
  expect(
    queried.every(
      (url) =>
        url.searchParams.get('date') === '2026-11-12' && url.searchParams.get('page') === '2',
    ),
  ).toBe(true);
  await expect(draft).toHaveValue('2026-11-14');
  await expect(draft).toBeFocused();
  await expect(page).toHaveURL('/games?date=2026-11-12&page=2');
  await page.getByRole('checkbox', { name: 'Auto-refresh', exact: true }).uncheck();
  await page.clock.fastForward(180_000);
  expect(checks).toBe(2);
});

test('retains roster focus and scroll through failed checks, then allows manual recovery while paused', async ({
  page,
}) => {
  await clock(page);
  let failing = false;
  let revision = false;
  let checks = 0;
  await page.route(/\/api\/v1\/games\/\d+\//, (route) => {
    checks += 1;
    if (failing)
      return route.fulfill({
        status: 503,
        contentType: 'text/html',
        body: '<h1>private upstream failure</h1>',
      });
    const data = gameDetail({ home_score: revision ? 5 : 2 });
    if (revision) data.freshness.checked_at = '2026-11-12T10:05:00Z';
    return route.fulfill({ json: data });
  });
  await page.goto('/games/2026020001');
  const controls = page.getByRole('region', { name: 'Saved data refresh', exact: true });
  const region = page.getByRole('region', { name: 'Away forwards', exact: true });
  await expect(region).toBeVisible();
  const previousCheck = (await controls.innerText()).split('Last checked:')[1]!;
  await region.evaluate((element) => {
    element.scrollLeft = 70;
  });
  const scrollLeft = await region.evaluate((element) => element.scrollLeft);
  await region.focus();
  failing = true;
  await page.clock.fastForward(60_000);
  await expect(controls).toContainText('Refresh failed. Displayed data is unchanged.');
  await expect(page.getByLabel('Home score: 2', { exact: true })).toHaveText('2');
  await expect(page.getByText('private upstream failure')).toHaveCount(0);
  expect((await controls.innerText()).split('Last checked:')[1]).toBe(previousCheck);
  await expect(region).toBeFocused();
  expect(await region.evaluate((element) => element.scrollLeft)).toBe(scrollLeft);
  await page.clock.fastForward(60_000);
  expect(checks).toBe(2); // First failure backs off to two minutes.
  await controls.getByRole('checkbox', { name: 'Auto-refresh', exact: true }).uncheck();
  failing = false;
  revision = true;
  const button = controls.getByRole('button', { name: 'Refresh now', exact: true });
  await button.click();
  await expect(page.getByLabel('Home score: 5', { exact: true })).toBeVisible();
  await expect(button).toBeFocused();
  await expect(controls).not.toContainText('Refresh failed.');
  expect(await region.evaluate((element) => element.scrollLeft)).toBe(scrollLeft);
  await page.clock.fastForward(180_000);
  expect(checks).toBe(3);
});

test('pauses hidden and offline tabs and checks once when they return', async ({
  page,
  context,
}) => {
  await clock(page);
  let checks = 0;
  await page.route(/\/api\/v1\/games\/\d+\//, (route) => {
    checks += 1;
    return route.fulfill({ json: gameDetail() });
  });
  await page.goto('/games/2026020001');
  await expect(page.getByRole('table', { name: 'Away forwards', exact: true })).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.fastForward(180_000);
  expect(checks).toBe(1);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => checks).toBe(2);
  await expect(page.getByText('Checking saved data…', { exact: true })).toHaveCount(0);
  await context.setOffline(true);
  await expect(
    page.getByText('Offline. Saved-data checks are paused.', { exact: true }),
  ).toBeVisible();
  await page.clock.fastForward(180_000);
  expect(checks).toBe(2);
  await context.setOffline(false);
  await expect.poll(() => checks).toBe(3);
});
