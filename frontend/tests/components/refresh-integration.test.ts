// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { gameDetail } from '../fixtures/game-detail.js';
import { gameDates, games } from '../fixtures/scoreboard.js';
import { REFRESH_INTERVAL_MS, SAVED_READ_TIMEOUT_MS } from '../../src/refresh/useSavedRefresh.js';

let wrapper: VueWrapper | undefined;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('scrollTo', vi.fn());
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
const json = (data: unknown) =>
  new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
async function render(path: string) {
  const router = createAppRouter(createMemoryHistory());
  await router.push(path);
  await router.isReady();
  wrapper = mount(App, { attachTo: document.body, global: { plugins: [router] } });
  await flushPromises();
  return { app: wrapper, router };
}

it('refreshes only the selected scoreboard date/page and keeps an unsubmitted date draft intact', async () => {
  const urls: URL[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (input) => {
      const url = new URL(String(input));
      urls.push(url);
      return json(url.pathname.endsWith('/dates/') ? gameDates() : games());
    }),
  );
  const { app, router } = await render('/games?date=2026-11-12&page=2');
  await app.get('input[type="date"]').setValue('2026-11-14');
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  await flushPromises();
  expect(urls).toHaveLength(4);
  expect(urls.every((url) => url.searchParams.get('date') === '2026-11-12')).toBe(true);
  expect(
    urls
      .filter((url) => url.pathname === '/api/v1/games/')
      .every((url) => url.searchParams.get('page') === '2'),
  ).toBe(true);
  expect((app.get('input[type="date"]').element as HTMLInputElement).value).toBe('2026-11-14');
  expect(router.currentRoute.value.fullPath).toBe('/games?date=2026-11-12&page=2');
});

it('pins an initially empty date store to its Pacific reference instead of adopting a later fallback during polling', async () => {
  const urls: URL[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (input) => {
      const url = new URL(String(input));
      urls.push(url);
      if (url.pathname.endsWith('/dates/'))
        return json(
          gameDates(
            url.searchParams.has('date')
              ? { selected_date: '2026-11-14', used_fallback: true }
              : {
                  selected_date: null,
                  latest_date: null,
                  reference_date: '2026-11-12',
                  window: [],
                },
          ),
        );
      return json(games('2026-11-12', []));
    }),
  );
  const { app, router } = await render('/games');
  expect(urls).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  await flushPromises();
  expect(urls.at(-1)!.searchParams.get('date')).toBe('2026-11-12');
  expect(app.get('h2').text()).toContain('November 12, 2026');
  expect(router.currentRoute.value.fullPath).toBe('/games');
});

it('retains saved rows/check time after a failed background read, then recovers without replacing table focus', async () => {
  let failing = false;
  let revision = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async () => {
      if (failing)
        return new Response('private proxy failure', {
          status: 503,
          headers: { 'Content-Type': 'text/html' },
        });
      const data = gameDetail({ home_score: revision ? 4 : 2 });
      if (revision) data.freshness.checked_at = '2026-11-12T10:02:00Z';
      return json(data);
    }),
  );
  const { app } = await render('/games/2026020001');
  const table = app.get('.table-scroll');
  (table.element as HTMLElement).focus();
  const initialCheck = app.get('.refresh-controls').text();
  failing = true;
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  await flushPromises();
  expect(app.text()).toContain('Refresh failed. Displayed data is unchanged.');
  expect(app.text()).not.toContain('private proxy failure');
  expect(app.get('[aria-label="Home score: 2"]').text()).toBe('2');
  expect(app.get('.refresh-controls').text()).toContain(
    initialCheck.slice(initialCheck.indexOf('Last checked:')),
  );
  expect(document.activeElement).toBe(table.element);
  failing = false;
  revision = 1;
  await app.get('.refresh-controls button').trigger('click');
  await flushPromises();
  expect(app.get('[aria-label="Home score: 4"]').text()).toBe('4');
  expect(app.text()).not.toContain('Refresh failed.');
  expect(document.activeElement).toBe(table.element);
});

it('times out a stalled background check without erasing the last valid game', async () => {
  let stall = false;
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>((_input, init) => {
      if (!stall) return Promise.resolve(json(gameDetail()));
      return new Promise((_resolve, reject) =>
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('Aborted', 'AbortError')),
          { once: true },
        ),
      );
    }),
  );
  const { app } = await render('/games/2026020001');
  stall = true;
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  expect(app.text()).toContain('Checking saved data');
  await vi.advanceTimersByTimeAsync(SAVED_READ_TIMEOUT_MS);
  await flushPromises();
  expect(app.text()).toContain('Refresh failed.');
  expect(app.findAll('table')).toHaveLength(3);
  expect(app.find('[role="alert"]').exists()).toBe(false);
});

it('cancels a pending check on game navigation and ignores its late payload', async () => {
  let calls = 0;
  let finish!: (response: Response) => void;
  let obsoleteSignal: AbortSignal | null | undefined;
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>((input, init) => {
      calls += 1;
      if (calls === 2) {
        obsoleteSignal = init?.signal;
        return new Promise((resolve) => {
          finish = resolve;
        });
      }
      return Promise.resolve(
        json(gameDetail({ home_score: String(input).includes('2026020002') ? 8 : 2 })),
      );
    }),
  );
  const { app, router } = await render('/games/2026020001');
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  await router.push('/games/2026020002');
  await flushPromises();
  expect(obsoleteSignal?.aborted).toBe(true);
  finish(json(gameDetail({ home_score: 9 })));
  await flushPromises();
  expect(app.get('[aria-label="Home score: 8"]').text()).toBe('8');
  expect(app.find('[aria-label="Home score: 9"]').exists()).toBe(false);
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  await flushPromises();
  expect(calls).toBe(4);
});

it('turns a stalled initial read into a retryable error instead of a permanent loading state', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true },
          );
        }),
    ),
  );
  const { app } = await render('/games/2026020001');
  expect(app.text()).toContain('Loading saved game');
  await vi.advanceTimersByTimeAsync(SAVED_READ_TIMEOUT_MS);
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Unable to load this saved game');
  expect(app.get('[role="alert"] button').text()).toBe('Try again');
});
