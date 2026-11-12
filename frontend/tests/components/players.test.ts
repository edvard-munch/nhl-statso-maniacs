// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { loadedSeasons, catalogue, filterMetadata } from '../fixtures/players.js';

let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'players-test' },
  });
type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;
function response(url: URL): Response {
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
async function render(path = '/players?season_id=20262027') {
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

it('pins the API default season and fetches independent complete metadata without paging/order', async () => {
  const fetch = mockApi();
  const { app, router } = await render('/players');
  expect(router.currentRoute.value.query.season_id).toBe('20262027');
  expect(app.text()).toContain('Season Skater');
  expect(app.text()).toContain('Partial');
  expect(app.text()).toContain('10:01');
  expect(app.text()).toContain('BUF, OLD');
  expect(app.findAll('tbody td').map((td) => td.text())).toContain('—');
  const urls = fetch.mock.calls.map(([input]) => new URL(String(input)));
  const metadata = urls.find((url) => url.pathname.endsWith('/filters/'))!;
  expect(metadata.searchParams.has('page')).toBe(false);
  expect(metadata.searchParams.has('page_size')).toBe(false);
  expect(metadata.searchParams.has('ordering')).toBe(false);
  expect(app.get('form').text()).toContain('Montreal Canadiens'); // Not on the single result page.
});
it('applies filters and preserves them through sorting, paging and back navigation', async () => {
  const fetch = mockApi((url) =>
    url.pathname === '/api/v1/players/'
      ? json(
          catalogue(url.searchParams, {
            count: 101,
            next: 'https://untrusted.example/page',
            previous: url.searchParams.get('page') === '2' ? '/ignored' : null,
          }),
        )
      : response(url),
  );
  const { app, router } = await render();
  await app.get('input[type="search"]').setValue('Name');
  await app.get('[aria-label="Points minimum"]').setValue('0');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({ search: 'Name', points_min: '0' });
  await app.get('[aria-label="Sort by Points"]').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.ordering).toBe('-points');
  await app.get('nav[aria-label="Players pages"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({
    page: '2',
    search: 'Name',
    points_min: '0',
    ordering: '-points',
  });
  expect(fetch.mock.calls.every(([input]) => !String(input).includes('untrusted.example'))).toBe(
    true,
  );
  router.back();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await flushPromises();
  expect(router.currentRoute.value.query.page).toBeUndefined();
  expect((app.get('input[type="search"]').element as HTMLInputElement).value).toBe('Name');
});
it('uses per-game and goalie contracts and clears incompatible draft filters on type switch', async () => {
  mockApi();
  const { app, router } = await render('/players?season_id=20262027&mode=averages&points_min=0.2');
  expect(app.text()).toContain('0.375');
  await app.findAll('select')[1]!.setValue('goalie');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({ player_type: 'goalie', mode: 'totals' });
  expect(router.currentRoute.value.query.points_min).toBeUndefined();
  expect(app.text()).toContain('Season Goalie');
  expect(app.text()).toContain('91.5%');
  expect(app.find('[aria-label="Sort by Goals"]').exists()).toBe(false);
});
it('keeps an explicit empty season rather than using old statistics', async () => {
  mockApi((url) =>
    url.pathname === '/api/v1/players/'
      ? json(catalogue(url.searchParams, { count: 0, results: [] }))
      : response(url),
  );
  const { app, router } = await render('/players?season_id=20272028');
  expect(router.currentRoute.value.query.season_id).toBe('20272028');
  expect(app.text()).toContain('No saved players match');
  expect(app.text()).not.toContain('Season Skater');
  expect(app.text()).toContain('2027–28');
});
it('rejects invalid routes without API reads and clears filters to recover', async () => {
  const fetch = mockApi();
  const { app } = await render('/players?season_id=20262027&page=0');
  expect(fetch).not.toHaveBeenCalled();
  expect(app.get('[role="alert"]').text()).toContain('positive page');
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(app.text()).toContain('Season Skater');
});
it('does not display previous rows when a new request fails and retries the selected page', async () => {
  let fail = false;
  mockApi((url) =>
    fail && url.pathname === '/api/v1/players/'
      ? json({ error: { code: 'not_found', message: 'internal detail', fields: {} } }, 404)
      : response(url),
  );
  const { app, router } = await render();
  fail = true;
  await router.push('/players?season_id=20252026&page=2');
  await flushPromises();
  expect(app.text()).not.toContain('Season Skater');
  expect(app.text()).not.toContain('internal detail');
  expect(app.get('[role="alert"]').text()).toContain('First page');
  fail = false;
  await app.get('[role="alert"] button:first-child').trigger('click');
  await flushPromises();
  expect(app.get('h2').text()).toContain('2025–26');
  expect(router.currentRoute.value.query.page).toBe('2');
});
it('discards a late response after a newer season selection even if transport ignores abort', async () => {
  let resolveOld!: (value: Response) => void;
  mockApi((url) =>
    url.pathname === '/api/v1/players/' && url.searchParams.get('season_id') === '20252026'
      ? new Promise((resolve) => {
          resolveOld = resolve;
        })
      : response(url),
  );
  const { app, router } = await render();
  await router.push('/players?season_id=20252026');
  await flushPromises();
  await router.push('/players?season_id=20262027&player_type=goalie');
  await flushPromises();
  resolveOld(json(catalogue()));
  await flushPromises();
  expect(app.text()).toContain('Season Goalie');
  expect(app.text()).not.toContain('Season Skater');
});
it('loads all season metadata pages without following response links', async () => {
  const fetch = mockApi((url) =>
    url.pathname.endsWith('/seasons/')
      ? json({
          ...loadedSeasons,
          results: [loadedSeasons.results[url.searchParams.get('page') === '2' ? 1 : 0]],
          next: url.searchParams.get('page') === '2' ? null : 'https://untrusted.example/seasons',
        })
      : response(url),
  );
  const { app } = await render();
  expect(app.findAll('select')[0]!.findAll('option')).toHaveLength(2);
  expect(
    fetch.mock.calls.filter(([input]) => new URL(String(input)).pathname.endsWith('/seasons/')),
  ).toHaveLength(2);
});

it('recovers from malformed season state using clear filters', async () => {
  mockApi();
  const { app, router } = await render('/players?season_id=2026-27');
  expect(app.get('[role="alert"]').text()).toContain('eight-digit');
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBe('20262027');
  expect(app.text()).toContain('Season Skater');
});

it('renders a genuinely empty loaded store without inventing a calendar season', async () => {
  mockApi((url) => {
    if (url.pathname.endsWith('/seasons/'))
      return json({
        count: 0,
        next: null,
        previous: null,
        results: [],
        meta: { default_season_id: null },
      });
    if (url.pathname.endsWith('/filters/')) {
      const metadata = filterMetadata();
      return json({
        ...metadata,
        meta: { ...metadata.meta, season_id: null },
        initial_count: 0,
        filtered_count: 0,
        options_count: 0,
        options: { teams: [], positions: [], nations: [] },
        initial_ranges: {},
        filtered_ranges: {},
        height_values_cm: [],
      });
    }
    const data = catalogue();
    return json({ ...data, meta: { ...data.meta, season_id: null }, count: 0, results: [] });
  });
  const { app, router } = await render('/players');
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
  expect(app.get('h2').text()).toContain('No loaded season');
  expect(app.text()).not.toContain('Season Skater');
});

it('bounds an unresponsive saved read and offers an explicit retry', async () => {
  vi.useFakeTimers();
  mockApi((url, init) =>
    url.pathname === '/api/v1/players/'
      ? new Promise((_resolve, reject) =>
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          ),
        )
      : response(url),
  );
  const { app } = await render();
  expect(app.text()).toContain('Loading saved players');
  await vi.advanceTimersByTimeAsync(10_000);
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Unable to load saved players');
  expect(app.find('tbody').exists()).toBe(false);
});
