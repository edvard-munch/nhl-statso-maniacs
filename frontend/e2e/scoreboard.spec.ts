import { expect, test, type Page } from '@playwright/test';
import { gameDates, games, game } from '../tests/fixtures/scoreboard.js';

test.use({ timezoneId: 'America/Los_Angeles' });

async function intercept(page: Page) {
  await page.route('**/api/v1/games/dates/**', (route) => {
    const date = new URL(route.request().url()).searchParams.get('date') ?? '2026-11-12';
    return route.fulfill({ json: gameDates({ requested_date: date, selected_date: date }) });
  });
  await page.route(/\/api\/v1\/games\/\?/, (route) => {
    const date = new URL(route.request().url()).searchParams.get('date')!;
    return route.fulfill({ json: games(date) });
  });
}

async function selectDate(page: Page, date: string) {
  await page.getByLabel('Schedule date', { exact: true }).fill(date);
  await page.getByRole('button', { name: 'Show games', exact: true }).click();
}

test('opens from home, discovers the Pacific date and preserves dates through navigation/reload', async ({
  page,
}) => {
  await intercept(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Browse games', exact: true }).click();
  await expect(page).toHaveURL('/games?date=2026-11-12');
  await expect(page.getByRole('heading', { level: 2 })).toHaveText('Thursday, November 12, 2026');
  await expect(page.getByLabel('Away score: 0', { exact: true })).toHaveText('0');
  await expect(page.getByText('State unknown', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Previous saved date', exact: true }).click();
  await expect(page).toHaveURL('/games?date=2026-11-10');
  await expect(page.getByRole('heading', { level: 2 })).toContainText('November 10, 2026');
  await page.goBack();
  await expect(page).toHaveURL('/games?date=2026-11-12');
  await expect(page.getByRole('heading', { level: 2 })).toContainText('November 12, 2026');
  await selectDate(page, '2026-11-14');
  await expect(page).toHaveURL('/games?date=2026-11-14');
  await page.reload();
  await expect(page.getByRole('heading', { level: 2 })).toContainText('November 14, 2026');
  const size = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(size.content).toBeLessThanOrEqual(size.viewport);
});

test('keeps an exact empty date and recovers from an API failure without displaying old games', async ({
  page,
}) => {
  await intercept(page);
  let failing = true;
  await page.route(/\/api\/v1\/games\/\?/, (route) => {
    const date = new URL(route.request().url()).searchParams.get('date')!;
    if (date === '2026-11-11') return route.fulfill({ json: games(date, []) });
    if (failing)
      return route.fulfill({
        status: 503,
        contentType: 'text/html',
        body: '<h1>private gateway detail</h1>',
      });
    return route.fulfill({ json: games(date) });
  });
  await page.goto('/games?date=2026-11-11');
  await expect(page.getByText('No saved games for this date.', { exact: true })).toBeVisible();
  await expect(page).toHaveURL('/games?date=2026-11-11');
  await selectDate(page, '2026-11-12');
  await expect(page.getByRole('alert')).toContainText('Unable to load saved games');
  await expect(page.getByText('private gateway detail')).toHaveCount(0);
  await expect(page.getByRole('article')).toHaveCount(0);
  failing = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('article')).toHaveCount(1);
});

test('shows null scores and conflicting evidence without turning them into zero or live', async ({
  page,
}) => {
  await intercept(page);
  await page.route(/\/api\/v1\/games\/\?/, (route) =>
    route.fulfill({
      json: games('2026-11-12', [
        game({
          away_team: null,
          away_score: null,
          home_score: 0,
          state: { value: 'unknown', conflict: true, observed_at: null, source: null },
        }),
      ]),
    }),
  );
  await page.goto('/games?date=2026-11-12');
  await expect(page.getByLabel('Away score: unavailable', { exact: true })).toHaveText('—');
  await expect(page.getByLabel('Home score: 0', { exact: true })).toHaveText('0');
  await expect(page.getByText('Away team unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Conflicting saved state', { exact: true })).toBeVisible();
  await expect(page.getByText('Saved as live', { exact: true })).toHaveCount(0);
});

test('paginates while retaining the date and resets page after another date is chosen', async ({
  page,
}) => {
  await intercept(page);
  await page.route(/\/api\/v1\/games\/\?/, (route) => {
    const url = new URL(route.request().url());
    const second = url.searchParams.get('page') === '2';
    return route.fulfill({
      json: games(url.searchParams.get('date')!, [game({ home_score: second ? 9 : 2 })], {
        count: 51,
        previous: second ? '/api/v1/games/?date=2026-11-12&page=1' : null,
        next: second ? null : '/api/v1/games/?date=2026-11-12&page=2',
      }),
    });
  });
  await page.goto('/games?date=2026-11-12');
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page).toHaveURL('/games?date=2026-11-12&page=2');
  await expect(page.getByLabel('Home score: 9', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next saved date', exact: true }).click();
  await expect(page).toHaveURL('/games?date=2026-11-14');
  await expect(page.getByLabel('Home score: 2', { exact: true })).toBeVisible();
});
