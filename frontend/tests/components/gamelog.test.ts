// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { profile, seasonHistory } from '../fixtures/profile.js';
import { gamelog, gamelogEntry } from '../fixtures/gamelog.js';
import { gameDetail, unknownSkaterStats } from '../fixtures/game-detail.js';
import { game } from '../fixtures/scoreboard.js';

let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'gamelog-test' },
  });
type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;
function response(url: URL) {
  const query = new URLSearchParams(url.searchParams);
  query.set('player_type', url.pathname.includes('/goalie/') ? 'goalie' : 'skater');
  if (url.pathname.includes('/games/')) return json(gameDetail());
  if (url.pathname.endsWith('/gamelog/')) return json(gamelog(query));
  return json(url.pathname.endsWith('/seasons/') ? seasonHistory(query) : profile(query));
}
function mockApi(handler: Handler = response) {
  const fetch = vi.fn<typeof globalThis.fetch>((input, init) =>
    Promise.resolve(handler(new URL(String(input)), init)),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
async function render(path = '/players/skater/8480001/gamelog') {
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
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('keeps omitted season as all saved dates and renders actual special-teams times, zero and unknown rows', async () => {
  const fetch = mockApi();
  const { app, router } = await render();
  expect(app.get('h1').text()).toBe('Profile Skater game log');
  expect(app.text()).toContain('All saved seasons and dates');
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
  const rows = app.findAll('tbody tr');
  expect(rows).toHaveLength(3);
  expect(rows[0]!.text()).toContain('12:34');
  expect(rows[0]!.text()).toContain('00:00');
  expect(rows[0]!.text()).toContain('01:35');
  expect(rows[1]!.text()).toContain('Unverified');
  expect(rows[1]!.find('a').exists()).toBe(false);
  expect(rows[1]!.findAll('td').every((td) => !['0', '00:00'].includes(td.text()))).toBe(true);
  expect(rows[2]!.text()).toContain('Date unavailable');
  expect(rows[2]!.text()).toContain('Missing');
  const url = new URL(
    String(fetch.mock.calls.find(([input]) => String(input).includes('/gamelog/'))![0]),
  );
  expect(url.searchParams.has('season_id')).toBe(false);
});
it('preserves profile/catalogue context through game navigation and excludes it from API queries', async () => {
  const fetch = mockApi();
  const context =
    '/players/skater/8480001?season_id=20262027&mode=averages&history_page=2&returnTo=' +
    encodeURIComponent('/players?season_id=20262027&page=2');
  const log =
    '/players/skater/8480001/gamelog?season_id=20262027&page=2&returnTo=' +
    encodeURIComponent(context);
  const { app, router } = await render(log);
  await app.get('tbody a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.gamelog).toBe(log);
  const back = app.findAll('main a').find((link) => link.text() === 'Back to player gamelog')!;
  expect(back.exists()).toBe(true);
  await back.trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(log);
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(context);
  const urls = fetch.mock.calls.map(([input]) => new URL(String(input)));
  expect(
    urls
      .filter((url) => url.pathname.endsWith('/gamelog/'))
      .every((url) => !url.searchParams.has('returnTo')),
  ).toBe(true);
  expect(urls.filter((url) => url.pathname.includes('/games/')).every((url) => !url.search)).toBe(
    true,
  );
  expect(
    urls
      .filter((url) => url.pathname.endsWith('/8480001/'))
      .every((url) => !url.searchParams.has('page') && !url.searchParams.has('returnTo')),
  ).toBe(true);
});
it('applies typed numeric/date/team filters, resets paging for sorting and preserves false/zero filters', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/gamelog/')
      ? json(gamelog(url.searchParams, { count: 101, next: 'https://not-followed.example/next' }))
      : response(url),
  );
  const { app, router } = await render('/players/skater/8480001/gamelog?season_id=20262027&page=2');
  await app.get('[aria-label="PP TOI (seconds) minimum"]').setValue('0');
  await app.get('[aria-label="Hits availability"]').setValue('false');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({
    pp_toi_seconds_min: '0',
    hits_isnull: 'false',
  });
  expect(router.currentRoute.value.query.page).toBeUndefined();
  await app.get('[aria-label="Sort by SH TOI (seconds)"]').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.ordering).toBe('-sh_toi_seconds');
  await app.get('[aria-label="Gamelog pages"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({
    page: '2',
    pp_toi_seconds_min: '0',
    hits_isnull: 'false',
    ordering: '-sh_toi_seconds',
  });
});
it('links selected-season and all-saved logs explicitly from profiles', async () => {
  mockApi();
  const { app, router } = await render('/players/skater/8480001?season_id=20262027');
  const links = app.findAll('main a');
  await links.find((link) => link.text() === 'View selected-season game log')!.trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBe('20262027');
  await app.get('main a').trigger('click');
  await flushPromises();
  await app
    .findAll('main a')
    .find((link) => link.text() === 'View all saved games')!
    .trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
});
it('renders goalie fields with rates and decision without mixing skater counts', async () => {
  mockApi();
  const { app } = await render('/players/goalie/8480001/gamelog');
  expect(app.get('h1').text()).toBe('Profile Goalie game log');
  expect(app.text()).toContain('90.6%');
  expect(app.find('[aria-label="Sort by Goals"]').exists()).toBe(false);
  expect(app.find('[aria-label="Sort by Decision"]').exists()).toBe(true);
});
it('keeps an explicit empty season and invalid filter recovery distinct from default selection', async () => {
  const fetch = mockApi((url) =>
    url.pathname.endsWith('/gamelog/')
      ? json(gamelog(url.searchParams, { count: 0, results: [] }))
      : response(url),
  );
  const { app, router } = await render('/players/skater/8480001/gamelog?season_id=20272028');
  expect(app.text()).toContain('No saved gamelog rows match');
  expect(router.currentRoute.value.query.season_id).toBe('20272028');
  fetch.mockClear();
  await router.push('/players/skater/8480001/gamelog?mode=averages');
  await flushPromises();
  expect(fetch).not.toHaveBeenCalled();
  expect(app.text()).toContain('unsupported');
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
  expect(app.text()).toContain('All saved seasons');
});
it('clears old rows on failures, keeps error references, and recovers to the first page', async () => {
  let fail = false;
  mockApi((url) =>
    fail && url.pathname.endsWith('/gamelog/')
      ? json({ error: { code: 'not_found', message: 'private error detail', fields: {} } }, 404)
      : response(url),
  );
  const { app, router } = await render();
  fail = true;
  await router.push('/players/skater/8480001/gamelog?page=9');
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.text()).not.toContain('Profile Skater');
  expect(app.text()).not.toContain('private error detail');
  expect(app.get('[role="alert"]').text()).toContain('gamelog-test');
  fail = false;
  await app.get('[role="alert"] button:nth-child(2)').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.page).toBe('1');
  expect(app.text()).toContain('Profile Skater game log');
});
it('does not expose late skater rows after navigating to the same ID in the goalie model', async () => {
  let resolveOld!: (response: Response) => void;
  mockApi((url) =>
    url.pathname.endsWith('/skater/8480001/gamelog/')
      ? new Promise((resolve) => {
          resolveOld = resolve;
        })
      : response(url),
  );
  const { app, router } = await render();
  await router.push('/players/goalie/8480001/gamelog');
  await flushPromises();
  resolveOld(json(gamelog()));
  await flushPromises();
  expect(app.get('h1').text()).toBe('Profile Goalie game log');
  expect(app.text()).not.toContain('01:35');
});
it('bounds stalled reads and retries GETs explicitly', async () => {
  vi.useFakeTimers();
  let fail = true;
  const fetch = mockApi((url, init) =>
    fail && url.pathname.endsWith('/gamelog/')
      ? new Promise((_resolve, reject) =>
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          ),
        )
      : response(url),
  );
  const { app } = await render();
  await vi.advanceTimersByTimeAsync(10_000);
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Unable to load this saved gamelog');
  fail = false;
  await app.get('[role="alert"] button:first-child').trigger('click');
  await flushPromises();
  expect(app.get('h1').text()).toBe('Profile Skater game log');
  expect(fetch.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true);
});
it('ignores unsafe game return context and retains the existing scoreboard fallback', async () => {
  mockApi();
  const { app } = await render('/games/2026020001?gamelog=https://evil.example/');
  expect(
    app
      .findAll('main a')
      .find((link) => link.text() === 'Back to games')!
      .attributes('href'),
  ).toBe('/games?date=2026-11-12');
  expect(app.text()).not.toContain('Back to player gamelog');
});

it('keeps a known conflicting game link separate from unverified player statistics', async () => {
  const entry = gamelogEntry({
    availability: 'unverified',
    stats: unknownSkaterStats(),
    game: {
      ...game(),
      state: { value: 'unknown', source: null, conflict: true, observed_at: null },
    },
  });
  mockApi((url) =>
    url.pathname.endsWith('/gamelog/')
      ? json(gamelog(url.searchParams, { count: 1, results: [entry] }))
      : response(url),
  );
  const { app } = await render();
  const row = app.get('tbody tr');
  expect(row.text()).toContain('Unverified');
  expect(row.text()).toContain('Conflicting saved state');
  expect(row.find('a').exists()).toBe(true);
  expect(
    row
      .findAll('td')
      .slice(7)
      .every((cell) => cell.text() === '—'),
  ).toBe(true);
  expect(row.text()).not.toContain('Saved as live');
});
