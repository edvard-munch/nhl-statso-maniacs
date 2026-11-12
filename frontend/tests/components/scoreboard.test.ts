// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { gameDates, games, game, freshness } from '../fixtures/scoreboard.js';

let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'scoreboard-test' },
  });
type Handler = (url: URL, init: RequestInit | undefined) => Response | Promise<Response>;
function mockApi(
  handler: Handler = (url) =>
    url.pathname.endsWith('/dates/')
      ? json(gameDates())
      : json(games(url.searchParams.get('date')!)),
) {
  const fetch = vi.fn<typeof globalThis.fetch>((input, init) =>
    Promise.resolve(handler(new URL(String(input)), init)),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
async function render(path = '/games?date=2026-11-12') {
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

it('loads through generated endpoints, preserving genuine zero, unknown state and missing scores', async () => {
  const fetch = mockApi((url) =>
    url.pathname.endsWith('/dates/')
      ? json(gameDates())
      : json(
          games('2026-11-12', [
            game({ home_score: null, home_team: null, freshness: freshness({ partial: true }) }),
          ]),
        ),
  );
  const { app } = await render();
  expect(app.get('[aria-label="Away score: 0"]').text()).toBe('0');
  expect(app.get('[aria-label="Home score: unavailable"]').text()).toBe('—');
  expect(app.text()).toContain('Home team unavailable');
  expect(app.text()).toContain('State unknown');
  expect(app.text()).not.toContain('Saved as live');
  expect(app.get('h2').text()).toBe('Thursday, November 12, 2026');
  const urls = fetch.mock.calls.map(([input]) => new URL(String(input)));
  expect(urls.map((url) => url.pathname).sort()).toEqual([
    '/api/v1/games/',
    '/api/v1/games/dates/',
  ]);
  expect(urls.find((url) => url.pathname === '/api/v1/games/')!.searchParams.get('date')).toBe(
    '2026-11-12',
  );
  expect(urls.find((url) => url.pathname === '/api/v1/games/')!.searchParams.get('page_size')).toBe(
    '50',
  );
});

it('uses API Pacific/default discovery only when date is omitted and puts selection in the URL', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/dates/')
      ? json(
          gameDates({
            requested_date: url.searchParams.get('date'),
            reference_date: '2026-11-12',
            selected_date: '2026-11-14',
            used_fallback: !url.searchParams.has('date'),
          }),
        )
      : json(games('2026-11-14')),
  );
  const { app, router } = await render('/games');
  await flushPromises();
  expect(router.currentRoute.value.query.date).toBe('2026-11-14');
  expect(app.get('h2').text()).toBe('Saturday, November 14, 2026');
  expect(app.text()).toContain('Latest saved date selected');
});

it('does not replace an explicitly requested unsaved date with navigation fallback', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/dates/')
      ? json(gameDates({ selected_date: '2026-11-14', used_fallback: true }))
      : json(games('2026-11-11', [])),
  );
  const { app, router } = await render('/games?date=2026-11-11');
  expect(router.currentRoute.value.query.date).toBe('2026-11-11');
  expect(app.text()).toContain('No saved games for this date.');
  expect(app.get('h2').text()).toContain('November 11, 2026');
  expect(app.get('.date-navigation button').attributes('disabled')).toBeDefined();
});

it('handles an empty date store without inventing a local date or requesting games', async () => {
  const fetch = mockApi(() =>
    json(
      gameDates({
        selected_date: null,
        latest_date: null,
        previous_date: null,
        next_date: null,
        window: [],
        reference_date: '2026-11-12',
      }),
    ),
  );
  const { app } = await render('/games');
  expect(app.text()).toContain('No saved game dates are available.');
  expect(fetch).toHaveBeenCalledTimes(1);
  expect((app.get('input').element as HTMLInputElement).value).toBe('2026-11-12');
});

it.each([
  '/games?date=2026-02-30',
  '/games?date=0000-01-01',
  '/games?date=2026-11-12&date=2026-11-14',
  '/games?date=2026-11-12&page=0',
  '/games?date=2026-11-12&page=1e2',
])('rejects invalid route values before fetching: %s', async (path) => {
  const fetch = mockApi();
  const { app } = await render(path);
  expect(app.get('[role="alert"]').text()).toContain('Choose a valid schedule date');
  expect(fetch).not.toHaveBeenCalled();
});

it('shows saved live/final/conflict evidence independently of the old completion flag', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/dates/')
      ? json(gameDates())
      : json(
          games(
            '2026-11-12',
            [
              game({
                nhl_id: 1,
                state: {
                  value: 'live',
                  source: 'legacy_result',
                  observed_at: null,
                  conflict: false,
                },
              }),
              game({
                nhl_id: 2,
                is_final: false,
                score_outcome: 'OT',
                state: {
                  value: 'final',
                  source: 'legacy_result',
                  observed_at: null,
                  conflict: false,
                },
              }),
              game({
                nhl_id: 3,
                is_final: true,
                state: { value: 'unknown', source: null, observed_at: null, conflict: true },
              }),
            ],
            {
              meta: { date: '2026-11-12', freshness: freshness({ is_stale: true, partial: true }) },
            },
          ),
        ),
  );
  const { app } = await render();
  expect(app.text()).toContain('Saved as live');
  expect(app.text()).toContain('Final (saved)');
  expect(app.text()).toContain('Overtime');
  expect(app.text()).toContain('Conflicting saved state');
  expect(app.text()).toContain('not current NHL observations');
  expect(app.text()).toContain('Saved data may be out of date');
});

it('shows a retryable error for a proxy HTML failure and recovers without exposing its body', async () => {
  let failed = true;
  mockApi((url) => {
    if (url.pathname.endsWith('/dates/')) return json(gameDates());
    return failed
      ? new Response('<script>private proxy detail</script>', {
          status: 502,
          headers: { 'Content-Type': 'text/html' },
        })
      : json(games());
  });
  const { app } = await render();
  expect(app.get('[role="alert"]').text()).toContain('Unable to load saved games');
  expect(app.text()).not.toContain('private proxy detail');
  failed = false;
  await app.get('[role="alert"] button').trigger('click');
  await flushPromises();
  expect(app.find('[role="alert"]').exists()).toBe(false);
  expect(app.findAll('.game-card')).toHaveLength(1);
});

it('cancels obsolete requests and ignores late responses', async () => {
  let resolveOld!: (response: Response) => void;
  let oldSignal: AbortSignal | undefined | null;
  mockApi((url, init) => {
    if (url.pathname.endsWith('/dates/')) return json(gameDates());
    if (url.searchParams.get('date') === '2026-11-12') {
      oldSignal = init?.signal;
      return new Promise((resolve) => {
        resolveOld = resolve;
      });
    }
    return json(games('2026-11-14', [game({ home_score: 8 })]));
  });
  const { app, router } = await render();
  expect(app.text()).toContain('Loading saved games');
  await router.push('/games?date=2026-11-14');
  await flushPromises();
  expect(oldSignal?.aborted).toBe(true);
  expect(app.get('[aria-label="Home score: 8"]').text()).toBe('8');
  resolveOld(json(games('2026-11-12')));
  await flushPromises();
  expect(app.get('h2').text()).toContain('November 14');
  expect(app.find('[aria-label="Home score: 2"]').exists()).toBe(false);
});

it('paginates without losing the schedule date and resets page when selecting another day', async () => {
  const fetch = mockApi((url) =>
    url.pathname.endsWith('/dates/')
      ? json(gameDates())
      : json(
          games('2026-11-12', [game()], {
            count: 51,
            next: '/api/v1/games/?date=2026-11-12&page=2',
          }),
        ),
  );
  const { app, router } = await render();
  await app.get('.pagination button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toEqual({ date: '2026-11-12', page: '2' });
  expect(fetch.mock.calls.some(([input]) => String(input).includes('page=2'))).toBe(true);
  await app.get('.date-window button:first-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toEqual({ date: '2026-11-10' });
});

it('clears visible old results while the newly selected date is loading', async () => {
  let resolveNext!: (response: Response) => void;
  mockApi((url) => {
    if (url.pathname.endsWith('/dates/')) return json(gameDates());
    if (url.searchParams.get('date') === '2026-11-14')
      return new Promise((resolve) => {
        resolveNext = resolve;
      });
    return json(games());
  });
  const { app, router } = await render();
  expect(app.findAll('.game-card')).toHaveLength(1);
  await router.push('/games?date=2026-11-14');
  await flushPromises();
  expect(app.text()).toContain('Loading saved games');
  expect(app.findAll('.game-card')).toHaveLength(0);
  expect(app.find('h2').exists()).toBe(false);
  resolveNext(json(games('2026-11-14')));
  await flushPromises();
  expect(app.get('h2').text()).toContain('November 14');
});

it('recovers from an unavailable page using page one and retains the API error reference', async () => {
  mockApi((url) => {
    if (url.pathname.endsWith('/dates/')) return json(gameDates());
    return url.searchParams.get('page') === '2'
      ? json({ error: { code: 'not_found', message: 'Not found.' } }, 404)
      : json(games());
  });
  const { app, router } = await render('/games?date=2026-11-12&page=2');
  expect(app.get('[role="alert"]').text()).toContain('That saved games page is unavailable');
  expect(app.get('[role="alert"]').text()).toContain('scoreboard-test');
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toEqual({ date: '2026-11-12' });
  expect(app.find('[role="alert"]').exists()).toBe(false);
  expect(app.findAll('.game-card')).toHaveLength(1);
});

it('reloads the selected date when its unchanged form is submitted', async () => {
  let score = 2;
  mockApi((url) =>
    url.pathname.endsWith('/dates/')
      ? json(gameDates())
      : json(games('2026-11-12', [game({ home_score: score })])),
  );
  const { app, router } = await render();
  score = 3;
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe('/games?date=2026-11-12');
  expect(app.get('[aria-label="Home score: 3"]').text()).toBe('3');
});
