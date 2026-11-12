// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import {
  emptyRoster,
  gameDetail,
  goalie,
  goalieStats,
  skater,
  skaterStats,
  unknownSkaterStats,
} from '../fixtures/game-detail.js';
import { gameDates, games } from '../fixtures/scoreboard.js';

let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'game-test-reference' },
  });
type Handler = (url: URL, init: RequestInit | undefined) => Response | Promise<Response>;
function mockApi(handler: Handler = () => json(gameDetail())) {
  const fetch = vi.fn<typeof globalThis.fetch>((input, init) =>
    Promise.resolve(handler(new URL(String(input)), init)),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
async function render(path = '/games/2026020001') {
  const router = createAppRouter(createMemoryHistory());
  await router.push(path);
  await router.isReady();
  wrapper = mount(App, { attachTo: document.body, global: { plugins: [router] } });
  await flushPromises();
  return { app: wrapper, router };
}
beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()));
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.unstubAllGlobals();
});

it('requests a typed ID without forwarding return-context queries and renders roster groups in saved order', async () => {
  const fetch = mockApi();
  const { app } = await render('/games/2026020001?date=2026-11-12&page=2');
  const url = new URL(String(fetch.mock.calls[0]![0]));
  expect(url.pathname).toBe('/api/v1/games/2026020001/');
  expect(url.search).toBe('');
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(app.get('.action-link').attributes('href')).toBe('/games?date=2026-11-12&page=2');
  expect(app.findAll('table caption').map((caption) => caption.text())).toEqual([
    'Away forwards',
    'Away defencemen',
    'Away goalies',
  ]);
  expect(app.findAll('.empty-roster')).toHaveLength(3);
  expect(app.get('tr[data-player-type="skater"][data-nhl-id="8480001"]').text()).toContain(
    'Alex Forward',
  );
  expect(app.get('tr[data-player-type="goalie"][data-nhl-id="8480001"]').text()).toContain(
    'Jamie Goalie',
  );
});

it('formats every saved skater/goalie unit, preserving zero TOI, negative plus/minus and null fractions', async () => {
  mockApi();
  const { app } = await render();
  const skaterCells = app
    .get('tr[data-player-type="skater"][data-nhl-id="8480001"]')
    .findAll('td')
    .map((cell) => cell.text());
  expect(skaterCells).toEqual([
    '7',
    'C',
    'Complete',
    '1',
    '0',
    '1',
    '-2',
    '0',
    '4',
    '0',
    '1',
    '3',
    '0',
    '0',
    '12:34',
    '00:00',
    '02:01',
  ]);
  const goalieCells = app
    .get('tr[data-player-type="goalie"]')
    .findAll('td')
    .map((cell) => cell.text());
  expect(goalieCells).toEqual(['30', 'G', 'Complete', 'W', '60:00', '2', '24', '26', '92.3%', '0']);
  expect(app.text()).toContain('Thursday, November 12, 2026');
});

it('keeps missing/unverified identities with unavailable stats and never borrows profile position', async () => {
  mockApi(() =>
    json(
      gameDetail({
        rosters: {
          away: {
            forwards: [
              skater({
                availability: 'unverified',
                game_position: null,
                sweater_number: null,
                stats: unknownSkaterStats(),
              }),
              skater({
                nhl_id: 8480003,
                name: 'Missing Player',
                availability: 'missing',
                game_position: null,
                sweater_number: null,
                stats: unknownSkaterStats(),
              }),
            ],
            defencemen: [],
            goalies: [],
          },
          home: emptyRoster(),
        },
      }),
    ),
  );
  const { app } = await render();
  const row = app.get('tr[data-nhl-id="8480001"]');
  expect(row.text()).toContain('Alex Forward');
  expect(row.findAll('td').map((cell) => cell.text())).toEqual([
    '—',
    '—',
    'Unverified',
    ...Array(14).fill('—'),
  ]);
  expect(row.text()).not.toContain('RW');
  expect(app.get('tr[data-nhl-id="8480003"]').text()).toContain('Missing');
});

it('retains valid fields in partial rows without deriving unknown totals, save percentage or shutouts', async () => {
  mockApi(() =>
    json(
      gameDetail({
        rosters: {
          away: {
            forwards: [
              skater({
                availability: 'partial',
                stats: skaterStats({ goals: 0, points: null, pp_toi_seconds: null }),
              }),
            ],
            defencemen: [],
            goalies: [
              goalie({
                availability: 'partial',
                stats: goalieStats({
                  goals_against: 0,
                  save_percentage: null,
                  shutouts: null,
                  decision: null,
                }),
              }),
            ],
          },
          home: emptyRoster(),
        },
      }),
    ),
  );
  const { app } = await render();
  expect(
    app
      .get('tr[data-player-type="skater"]')
      .findAll('td')
      .map((cell) => cell.text()),
  ).toEqual([
    '7',
    'C',
    'Partial',
    '0',
    '0',
    '—',
    '-2',
    '0',
    '4',
    '0',
    '1',
    '3',
    '0',
    '0',
    '12:34',
    '—',
    '02:01',
  ]);
  expect(
    app
      .get('tr[data-player-type="goalie"]')
      .findAll('td')
      .map((cell) => cell.text()),
  ).toEqual(['30', 'G', 'Partial', '—', '60:00', '0', '24', '26', '—', '—']);
});

it('renders undated games with missing sides and empty rosters without inventing a schedule date', async () => {
  mockApi(() =>
    json(
      gameDetail({
        date: null,
        away_team: null,
        home_team: null,
        away_score: null,
        home_score: null,
        rosters: { away: emptyRoster(), home: emptyRoster() },
      }),
    ),
  );
  const { app } = await render();
  expect(app.text()).toContain('Schedule date unavailable');
  expect(app.text()).not.toContain('Pacific schedule date:');
  expect(app.findAll('table')).toHaveLength(0);
  expect(app.findAll('.empty-roster')).toHaveLength(6);
  expect(app.get('.action-link').attributes('href')).toBe('/games');
});

it('ignores invalid return context and arbitrary redirect URLs', async () => {
  mockApi();
  const { app } = await render('/games/2026020001?date=bad&page=-1&next=https://example.com');
  expect(app.get('.action-link').attributes('href')).toBe('/games?date=2026-11-12');
});

it.each(['/games/not-a-number', '/games/0', '/games/-1', '/games/9007199254740992'])(
  'rejects invalid game identities before fetching: %s',
  async (path) => {
    const fetch = mockApi();
    const { app } = await render(path);
    expect(app.get('[role="alert"]').text()).toContain('Game not found');
    expect(fetch).not.toHaveBeenCalled();
  },
);

it('distinguishes an unknown saved game from a transient server failure', async () => {
  mockApi(() => json({ error: { code: 'not_found', message: 'Not found.' } }, 404));
  const { app } = await render();
  expect(app.get('[role="alert"]').text()).toContain('Game not found');
  expect(app.find('[role="alert"] button').exists()).toBe(false);
});

it('retries transient API errors and preserves their correlation reference', async () => {
  let failing = true;
  mockApi(() =>
    failing
      ? json({ error: { code: 'server_error', message: 'Unavailable.' } }, 500)
      : json(gameDetail()),
  );
  const { app } = await render();
  expect(app.get('[role="alert"]').text()).toContain('game-test-reference');
  failing = false;
  await app.get('[role="alert"] button').trigger('click');
  await flushPromises();
  expect(app.find('[role="alert"]').exists()).toBe(false);
  expect(app.findAll('table')).toHaveLength(3);
});

it('does not expose a non-JSON proxy failure', async () => {
  mockApi(
    () =>
      new Response('<h1>private gateway text</h1>', {
        status: 502,
        headers: { 'Content-Type': 'text/html' },
      }),
  );
  const { app } = await render();
  expect(app.get('[role="alert"]').text()).toContain('Unable to load this saved game');
  expect(app.text()).not.toContain('private gateway text');
});

it('clears old game rows, aborts outdated reads and ignores late responses when the game ID changes', async () => {
  let resolveFirst!: (response: Response) => void;
  let firstSignal: AbortSignal | null | undefined;
  mockApi((url, init) => {
    if (url.pathname.endsWith('/2026020001/')) {
      firstSignal = init?.signal;
      return new Promise((resolve) => {
        resolveFirst = resolve;
      });
    }
    return json(gameDetail({ nhl_id: 2026020002, home_score: 8 }));
  });
  const { app, router } = await render();
  expect(app.text()).toContain('Loading saved game');
  await router.push('/games/2026020002');
  await flushPromises();
  expect(firstSignal?.aborted).toBe(true);
  expect(app.get('[aria-label="Home score: 8"]').text()).toBe('8');
  resolveFirst(json(gameDetail()));
  await flushPromises();
  expect(app.get('[aria-label="Home score: 8"]').text()).toBe('8');
  expect(app.find('[aria-label="Home score: 2"]').exists()).toBe(false);
});

it('aborts in-flight detail requests when leaving the view', async () => {
  let signal: AbortSignal | null | undefined;
  let resolve!: (response: Response) => void;
  mockApi((_url, init) => {
    signal = init?.signal;
    return new Promise((done) => {
      resolve = done;
    });
  });
  const { app, router } = await render();
  await router.push('/');
  await flushPromises();
  expect(signal?.aborted).toBe(true);
  resolve(json(gameDetail()));
  await flushPromises();
  expect(app.find('table').exists()).toBe(false);
  expect(app.text()).toContain('Follow NHL games and players');
});

it('links from a scoreboard page and returns to its exact date and page', async () => {
  const fetch = mockApi((url) => {
    if (url.pathname.endsWith('/dates/')) return json(gameDates());
    if (url.pathname === '/api/v1/games/') return json(games());
    return json(gameDetail());
  });
  const { app, router } = await render('/games?date=2026-11-12&page=2');
  const link = app.get('.game-card a');
  expect(link.attributes('href')).toBe('/games/2026020001?date=2026-11-12&page=2');
  await link.trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.name).toBe('game-detail');
  expect(app.findAll('.game-card a')).toHaveLength(0);
  await app.get('.action-link').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe('/games?date=2026-11-12&page=2');
  expect(
    fetch.mock.calls.some(([input]) => String(input).endsWith('/api/v1/games/2026020001/')),
  ).toBe(true);
});

it('hides an already loaded roster while a different game is pending or fails', async () => {
  let finish!: (response: Response) => void;
  mockApi((url) =>
    url.pathname.endsWith('/2026020001/')
      ? json(gameDetail())
      : new Promise((resolve) => {
          finish = resolve;
        }),
  );
  const { app, router } = await render();
  expect(app.findAll('table')).toHaveLength(3);
  await router.push('/games/2026020002');
  await flushPromises();
  expect(app.text()).toContain('Loading saved game');
  expect(app.findAll('table')).toHaveLength(0);
  expect(app.text()).not.toContain('Alex Forward');
  finish(json({ error: { code: 'server_error', message: 'Unavailable.' } }, 500));
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Unable to load this saved game');
  expect(app.findAll('table')).toHaveLength(0);
});

it('keeps a known zero goalie save percentage and zero ice time distinct from missing values', async () => {
  mockApi(() =>
    json(
      gameDetail({
        rosters: {
          away: {
            forwards: [],
            defencemen: [],
            goalies: [goalie({ stats: goalieStats({ save_percentage: 0, toi_seconds: 0 }) })],
          },
          home: emptyRoster(),
        },
      }),
    ),
  );
  const { app } = await render();
  const cells = app
    .get('tr[data-player-type="goalie"]')
    .findAll('td')
    .map((cell) => cell.text());
  expect(cells).toContain('0.0%');
  expect(cells).toContain('00:00');
});
