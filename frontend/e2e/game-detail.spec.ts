import { expect, test, type Page } from './fixtures.js';
import {
  emptyRoster,
  gameDetail,
  skater,
  unknownSkaterStats,
} from '../tests/fixtures/game-detail.js';
import { gameDates, games } from '../tests/fixtures/scoreboard.js';

async function intercept(page: Page) {
  await page.route('**/api/v1/games/dates/**', (route) => route.fulfill({ json: gameDates() }));
  await page.route(/\/api\/v1\/games\/\?/, (route) =>
    route.fulfill({
      json: games('2026-11-12', undefined, {
        count: 51,
        previous: '/api/v1/games/?date=2026-11-12&page=1',
      }),
    }),
  );
  await page.route(/\/api\/v1\/games\/\d+\//, (route) => route.fulfill({ json: gameDetail() }));
}

test('opens a saved game, reloads its URL and returns to the same scoreboard page', async ({
  page,
}) => {
  const requests: string[] = [];
  page.on('request', (request) => {
    if (/\/api\/v1\/games\/\d+\//.test(request.url())) requests.push(request.url());
  });
  await intercept(page);
  await page.goto('/games?date=2026-11-12&page=2');
  await page.getByRole('link', { name: 'View game details', exact: true }).click();
  await expect(page).toHaveURL('/games/2026020001?date=2026-11-12&page=2');
  await expect(page).toHaveTitle('Game details | NHL Statso Maniacs');
  await expect(page.getByRole('table', { name: 'Away forwards', exact: true })).toBeVisible();
  const skater = page.locator('tr[data-player-type="skater"][data-nhl-id="8480001"]');
  await expect(skater.getByRole('cell', { name: '12:34', exact: true })).toBeVisible();
  await expect(skater.getByRole('cell', { name: '00:00', exact: true })).toBeVisible();
  await expect(page.locator('tr[data-player-type="goalie"]')).toContainText('92.3%');
  expect(requests.every((url) => new URL(url).search === '')).toBe(true);
  await page.reload();
  await expect(page.getByRole('rowheader', { name: 'Alex Forward', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Back to games', exact: true }).click();
  await expect(page).toHaveURL('/games?date=2026-11-12&page=2');
  await page.goBack();
  await expect(page).toHaveURL('/games/2026020001?date=2026-11-12&page=2');
  await expect(page.getByRole('table', { name: 'Away goalies', exact: true })).toBeVisible();
});

test('keeps wide roster tables inside the viewport and keyboard-scrollable', async ({ page }) => {
  await intercept(page);
  await page.goto('/games/2026020001');
  const region = page.getByRole('region', { name: 'Away forwards', exact: true });
  await expect(region).toBeVisible();
  const documentSize = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(documentSize.width).toBeLessThanOrEqual(documentSize.viewport);
  const tableSize = await region.evaluate((element) => ({
    width: element.clientWidth,
    content: element.scrollWidth,
  }));
  if (page.viewportSize()!.width <= 360) expect(tableSize.content).toBeGreaterThan(tableSize.width);
  await region.focus();
  await expect(region).toBeFocused();
  if (tableSize.content > tableSize.width) {
    await page.keyboard.press('ArrowRight');
    await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  }
});

test('preserves unverified identity, undated games, unknown scores and conflicting saved state', async ({
  page,
}) => {
  await intercept(page);
  await page.route(/\/api\/v1\/games\/\d+\//, (route) =>
    route.fulfill({
      json: gameDetail({
        date: null,
        away_score: 0,
        home_score: null,
        is_final: true,
        state: { value: 'unknown', conflict: true, source: null, observed_at: null },
        rosters: {
          away: {
            forwards: [
              skater({
                availability: 'unverified',
                sweater_number: null,
                game_position: null,
                stats: unknownSkaterStats(),
              }),
            ],
            defencemen: [],
            goalies: [],
          },
          home: emptyRoster(),
        },
      }),
    }),
  );
  await page.goto('/games/2026020001');
  await expect(page.getByText('Schedule date unavailable.', { exact: false })).toBeVisible();
  await expect(page.getByLabel('Away score: 0', { exact: true })).toHaveText('0');
  await expect(page.getByLabel('Home score: unavailable', { exact: true })).toHaveText('—');
  await expect(page.getByText('Conflicting saved state', { exact: true })).toBeVisible();
  const row = page.locator('tr[data-player-type="skater"]');
  await expect(row.getByRole('rowheader')).toHaveText('Alex Forward');
  await expect(row.getByRole('cell', { name: 'Unverified', exact: true })).toBeVisible();
  await expect(row.getByRole('cell', { name: '—', exact: true })).toHaveCount(16);
  await expect(
    page.getByText('No saved players in this roster group.', { exact: true }),
  ).toHaveCount(5);
});

test('distinguishes missing games from transient failures and recovers on retry', async ({
  page,
}) => {
  await intercept(page);
  let failed = true;
  await page.route(/\/api\/v1\/games\/\d+\//, (route) => {
    if (route.request().url().includes('2026020099'))
      return route.fulfill({
        status: 404,
        json: { error: { code: 'not_found', message: 'Not found.' } },
      });
    return failed
      ? route.fulfill({
          status: 502,
          contentType: 'text/html',
          body: '<h1>private upstream detail</h1>',
        })
      : route.fulfill({ json: gameDetail() });
  });
  await page.goto('/games/2026020099');
  await expect(page.getByRole('alert')).toContainText('Game not found');
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(0);
  await page.goto('/games/2026020001');
  await expect(page.getByRole('alert')).toContainText('Unable to load this saved game');
  await expect(page.getByText('private upstream detail')).toHaveCount(0);
  await expect(page.getByRole('table')).toHaveCount(0);
  failed = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('table', { name: 'Away forwards', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
