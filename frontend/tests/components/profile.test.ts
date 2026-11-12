// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { profile, seasonHistory } from '../fixtures/profile.js';
import { catalogue, filterMetadata, loadedSeasons } from '../fixtures/players.js';

let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'profile-test' },
  });
type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;
function response(url: URL): Response {
  if (/\/players\/(skater|goalie)\//.test(url.pathname)) {
    const query = new URLSearchParams(url.searchParams);
    query.set('player_type', url.pathname.includes('/goalie/') ? 'goalie' : 'skater');
    return json(url.pathname.endsWith('/seasons/') ? seasonHistory(query) : profile(query));
  }
  if (url.pathname.endsWith('/seasons/')) return json(loadedSeasons);
  return json(
    url.pathname.endsWith('/filters/')
      ? filterMetadata(url.searchParams)
      : catalogue(url.searchParams),
  );
}
function mockApi(handler: Handler = response) {
  const fetch = vi.fn<typeof globalThis.fetch>((input, init) =>
    Promise.resolve(handler(new URL(String(input)), init)),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
async function render(path = '/players/skater/8480001?season_id=20262027') {
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

it('links a typed catalogue identity and preserves its complete applied return context', async () => {
  const fetch = mockApi();
  const context = '/players?season_id=20262027&mode=averages&team=BUF&page=2';
  const { app, router } = await render(context);
  await app.get('tbody a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.params).toEqual({ playerType: 'skater', nhlId: '8480001' });
  expect(router.currentRoute.value.query).toMatchObject({
    mode: 'averages',
    season_id: '20262027',
    returnTo: context,
  });
  expect(app.get('h1').text()).toBe('Profile Skater');
  const urls = fetch.mock.calls.map(([input]) => new URL(String(input)));
  const detail = urls.find((url) => url.pathname === '/api/v1/players/skater/8480001/')!;
  expect([...detail.searchParams.keys()].sort()).toEqual(['mode', 'season_id']);
  const history = urls.find((url) => url.pathname.endsWith('/8480001/seasons/'))!;
  expect([...history.searchParams.keys()].sort()).toEqual(['mode', 'page', 'page_size']);
  expect(urls.some((url) => url.hostname === 'not-followed.example')).toBe(false);
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(context);
});
it('keeps selected season, career and exact split availability independent', async () => {
  mockApi();
  const { app } = await render();
  expect(app.text()).toContain('Current saved biography');
  expect(app.text()).toContain('Buffalo Sabres');
  const packets = app.get('[aria-label="Selected season and career statistics"]');
  const rows = packets.findAll('tbody tr');
  expect(rows).toHaveLength(3);
  expect(rows[0]!.text()).toContain('2026–27');
  expect(rows[1]!.text()).toContain('120');
  expect(rows[2]!.text()).toContain('1.2');
  expect(packets.text()).toContain('00:00');
  expect(packets.text()).toContain('—');
  const history = app.get('[aria-label="Season history and team contributions"]');
  const split = history.findAll('tbody tr').find((row) => row.text().includes('BUF contribution'))!;
  expect(split.text()).toContain('Unverified');
  expect(
    split
      .findAll('td')
      .slice(1)
      .every((td) => td.text() === '—'),
  ).toBe(true);
  expect(
    history
      .findAll('tbody tr')
      .find((row) => row.text().includes('2025–26 · overall'))!
      .findAll('td')[1]!
      .text(),
  ).toBe('0');
});
it('keeps an explicit missing season without replacing career packets or substituting prior statistics', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/8480001/')
      ? json(
          profile(url.searchParams, { selected_season: { availability: 'missing', stats: null } }),
        )
      : response(url),
  );
  const { app, router } = await render('/players/skater/8480001?season_id=20272028');
  expect(router.currentRoute.value.query.season_id).toBe('20272028');
  const rows = app.get('[aria-label="Selected season and career statistics"]').findAll('tbody tr');
  expect(rows[0]!.text()).toContain('Missing');
  expect(
    rows[0]!
      .findAll('td')
      .slice(1)
      .every((td) => td.text() === '—'),
  ).toBe(true);
  expect(rows[1]!.text()).toContain('120');
});
it('pins the API-resolved season without forwarding browser-only context', async () => {
  const fetch = mockApi();
  const { router, app } = await render('/players/skater/8480001');
  expect(router.currentRoute.value.query.season_id).toBe('20262027');
  expect(app.get('h1').text()).toBe('Profile Skater');
  expect(
    fetch.mock.calls.filter(([input]) => new URL(String(input)).pathname.endsWith('/8480001/')),
  ).toHaveLength(2);
});
it('allows profiles with no loaded season and no season history', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/seasons/')
      ? json(seasonHistory(url.searchParams, { count: 0, results: [] }))
      : json(
          profile(url.searchParams, {
            meta: { player_type: 'skater', mode: 'totals', season_id: null },
            selected_season: { availability: 'missing', stats: null },
            career_averages: null,
          }),
        ),
  );
  const { app, router } = await render('/players/skater/8480001');
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
  expect(app.get('h1').text()).toBe('Profile Skater');
  expect(app.text()).toContain('No loaded season');
  expect(app.text()).toContain('No saved season history.');
});
it('applies mode/season choices and preserves explicit history pagination in the URL', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/8480001/seasons/')
      ? json(
          seasonHistory(url.searchParams, { count: 51, next: 'https://not-followed.example/page' }),
        )
      : response(url),
  );
  const { app, router } = await render();
  await app.get('#profile-mode').setValue('averages');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query.mode).toBe('averages');
  expect(app.get('[aria-label="Selected season and career statistics"]').text()).toContain('1.25');
  await app.get('[aria-label="History pages"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.history_page).toBe('2');
  expect(router.currentRoute.value.query.mode).toBe('averages');
  await app.get('#profile-season').setValue('20252026');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBe('20252026');
  expect(router.currentRoute.value.query.history_page).toBeUndefined();
});
it('keeps biography and career packets visible when a history page fails and recovers to page one', async () => {
  let fail = true;
  mockApi((url) =>
    fail && url.pathname.endsWith('/8480001/seasons/')
      ? json({ error: { code: 'not_found', message: 'private detail', fields: {} } }, 404)
      : response(url),
  );
  const { app, router } = await render('/players/skater/8480001?season_id=20262027&history_page=3');
  expect(app.get('h1').text()).toBe('Profile Skater');
  expect(app.text()).toContain('Career totals');
  expect(app.text()).not.toContain('private detail');
  expect(app.text()).toContain('Unable to load this history page');
  fail = false;
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.history_page).toBe('1');
  expect(app.find('[role="alert"]').exists()).toBe(false);
});
it('uses the goalie model explicitly and omits career-average controls', async () => {
  const fetch = mockApi();
  const { app } = await render('/players/goalie/8480001?season_id=20262027');
  expect(app.get('h1').text()).toBe('Profile Goalie');
  const table = app.get('[aria-label="Selected season and career statistics"]');
  expect(table.findAll('tbody tr')).toHaveLength(2);
  expect(table.text()).toContain('91.5%');
  expect(app.find('#profile-mode option[value="averages"]').exists()).toBe(false);
  expect(fetch.mock.calls.every(([input]) => !String(input).includes('/skater/'))).toBe(true);
});
it('rejects invalid identities without reads and invalid selections with default recovery', async () => {
  const fetch = mockApi();
  const { app, router } = await render('/players/goalie/0');
  expect(fetch).not.toHaveBeenCalled();
  expect(app.text()).toContain('Player not found');
  await router.push('/players/goalie/8480001?mode=averages');
  await flushPromises();
  expect(fetch).not.toHaveBeenCalled();
  expect(app.text()).toContain('goalie totals');
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(app.get('h1').text()).toBe('Profile Goalie');
});
it('clears stale identity/statistics during an error and discards late results after navigation', async () => {
  let resolveOld!: (response: Response) => void;
  mockApi((url) =>
    url.pathname.endsWith('/8480002/')
      ? new Promise((resolve) => {
          resolveOld = resolve;
        })
      : response(url),
  );
  const { app, router } = await render();
  await router.push('/players/skater/8480002?season_id=20262027');
  await flushPromises();
  expect(app.text()).not.toContain('Career totals');
  expect(app.text()).not.toContain('Profile Skater');
  await router.push('/players/goalie/8480001?season_id=20262027');
  await flushPromises();
  resolveOld(json(profile()));
  await flushPromises();
  expect(app.get('h1').text()).toBe('Profile Goalie');
});
it('bounds stalled profile reads and supports retry without replaying any write', async () => {
  vi.useFakeTimers();
  let fail = true;
  const fetch = mockApi((url, init) =>
    fail
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
  expect(app.get('[role="alert"]').text()).toContain('Unable to load this saved player');
  fail = false;
  await app.get('[role="alert"] button:first-child').trigger('click');
  await flushPromises();
  expect(app.get('h1').text()).toBe('Profile Skater');
  expect(fetch.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true);
});

it('reports a saved-profile 404 without trying the other player model', async () => {
  const fetch = mockApi(() =>
    json({ error: { code: 'not_found', message: 'private lookup detail', fields: {} } }, 404),
  );
  const { app } = await render('/players/goalie/8480001?season_id=20262027');
  expect(app.text()).toContain('Player not found');
  expect(app.text()).not.toContain('private lookup detail');
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(String(fetch.mock.calls[0]![0])).toContain('/goalie/');
});

it('bounds a stalled history read while keeping the confirmed profile visible', async () => {
  vi.useFakeTimers();
  mockApi((url, init) =>
    url.pathname.endsWith('/8480001/seasons/')
      ? new Promise((_resolve, reject) =>
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          ),
        )
      : response(url),
  );
  const { app } = await render();
  expect(app.get('h1').text()).toBe('Profile Skater');
  await vi.advanceTimersByTimeAsync(10_000);
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Unable to load this history page');
  expect(app.get('h1').text()).toBe('Profile Skater');
  expect(app.text()).toContain('Career totals');
});
