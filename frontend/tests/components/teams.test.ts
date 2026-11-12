// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { teams, teamDetail, teamPlayers } from '../fixtures/teams.js';
import { profile, profileStats, seasonHistory } from '../fixtures/profile.js';

let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'team-test' },
  });
type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;
function response(url: URL): Response {
  if (url.pathname === '/api/v1/teams/') return json(teams(url.searchParams));
  if (url.pathname.endsWith('/players/')) return json(teamPlayers(url.searchParams));
  if (url.pathname.startsWith('/api/v1/teams/')) return json(teamDetail(url.searchParams));
  if (url.pathname.endsWith('/seasons/')) return json(seasonHistory(url.searchParams));
  return json(
    profile(url.searchParams, {
      selected_season: {
        availability: 'partial',
        stats: profileStats({ games: 10, goals: 4, assists: 4, points: 8 }),
      },
    }),
  );
}
function mockApi(handler: Handler = response) {
  const fetch = vi.fn<typeof globalThis.fetch>((input, init) =>
    Promise.resolve(handler(new URL(String(input)), init)),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
async function render(path = '/teams/7?season_id=20262027') {
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

it('lists saved historical identities with missing metadata rather than inventing active status', async () => {
  mockApi();
  const { app } = await render('/teams');
  expect(app.get('h1').text()).toBe('Teams');
  expect(app.text()).toContain('Historical Team');
  const row = app.findAll('tbody tr')[1]!;
  expect(row.findAll('td').map((cell) => cell.text())).toContain('—');
  expect(app.text()).toContain('does not establish active status');
});
it('filters and paginates the directory through URL state and preserves it through detail navigation', async () => {
  const fetch = mockApi((url) =>
    url.pathname === '/api/v1/teams/'
      ? json(teams(url.searchParams, { count: 101, next: 'https://not-followed.example/next' }))
      : response(url),
  );
  const { app, router } = await render('/teams');
  await app.get('input[type="search"]').setValue('BUF');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query.search).toBe('BUF');
  await app.get('[aria-label="Teams pages"] button:last-child').trigger('click');
  await flushPromises();
  const context = router.currentRoute.value.fullPath;
  await app.get('tbody a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.returnTo).toBe(context);
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(context);
  expect(fetch.mock.calls.every(([input]) => !String(input).includes('not-followed.example'))).toBe(
    true,
  );
});
it('uses exact team contributions rather than overall stats and preserves team context through profiles', async () => {
  const fetch = mockApi();
  const { app, router } = await render(
    '/teams/7?season_id=20262027&page=2&returnTo=%2Fteams%3Fconference%3DEastern',
  );
  const context = router.currentRoute.value.fullPath;
  const cells = app
    .get('tbody tr')
    .findAll('td')
    .map((cell) => cell.text());
  expect(cells).toEqual(expect.arrayContaining(['6', '3', '18:31', '00:00', '—', '0']));
  await app.get('tbody a').trigger('click');
  await flushPromises();
  expect(app.get('h1').text()).toBe('Profile Skater');
  expect(
    app
      .findAll('main a')
      .find((link) => link.text() === 'Back to team')!
      .attributes('href'),
  ).toBe(context);
  expect(
    app
      .get('[aria-label="Selected season and career statistics"]')
      .findAll('tbody tr')[0]!
      .findAll('td')
      .map((cell) => cell.text()),
  ).toEqual(expect.arrayContaining(['10', '4']));
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(context);
  const urls = fetch.mock.calls.map(([input]) => new URL(String(input)));
  expect(
    urls
      .filter((url) => url.pathname === '/api/v1/teams/7/')
      .every((url) => [...url.searchParams.keys()].every((key) => key === 'season_id')),
  ).toBe(true);
  expect(
    urls
      .filter((url) => url.pathname === '/api/v1/teams/7/players/')
      .every((url) => !url.searchParams.has('returnTo') && !url.searchParams.has('team')),
  ).toBe(true);
  expect(urls.some((url) => url.pathname === '/api/v1/players/filters/')).toBe(false);
});
it('pins only the globally resolved season and keeps explicit empty seasons selected', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/players/')
      ? json(
          teamPlayers(
            url.searchParams,
            url.searchParams.get('season_id') === '20272028' ? { count: 0, results: [] } : {},
          ),
        )
      : response(url),
  );
  const { app, router } = await render('/teams/7');
  expect(router.currentRoute.value.query.season_id).toBe('20262027');
  await router.push('/teams/7?season_id=20272028');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBe('20272028');
  expect(app.text()).toContain('No saved team contributions match');
  expect(app.find('tbody').exists()).toBe(false);
});
it('shows known team metadata with no globally loaded seasons or contributions', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/players/')
      ? json({
          ...teamPlayers(),
          count: 0,
          results: [],
          meta: { ...teamPlayers().meta, season_id: null },
        })
      : json(teamDetail(url.searchParams, { meta: { season_id: null } })),
  );
  const { app, router } = await render('/teams/7');
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
  expect(app.get('h1').text()).toBe('Buffalo Sabres');
  expect(app.text()).toContain('No loaded season');
});
it('uses split averages and goalie fields without leaking incompatible filters', async () => {
  mockApi();
  const { app, router } = await render('/teams/7?season_id=20262027&mode=averages&goals_min=0.5');
  expect(app.get('tbody').text()).toContain('0.5');
  await app.findAll('select')[0]!.setValue('goalie');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query.player_type).toBe('goalie');
  expect(router.currentRoute.value.query.mode).toBe('totals');
  expect(router.currentRoute.value.query.goals_min).toBeUndefined();
  expect(app.get('tbody').text()).toContain('Split Goalie');
  expect(app.get('tbody').text()).toContain('90.0%');
  expect(app.find('[aria-label="Sort by Goals"]').exists()).toBe(false);
});
it('retains zero/false filters while sorting and paging and resets page on apply', async () => {
  mockApi((url) =>
    url.pathname.endsWith('/players/')
      ? json(
          teamPlayers(url.searchParams, { count: 101, next: 'https://not-followed.example/next' }),
        )
      : response(url),
  );
  const { app, router } = await render('/teams/7?season_id=20262027&page=2');
  await app.get('[aria-label="Goals minimum"]').setValue('0');
  await app.get('[aria-label="Hits availability"]').setValue('false');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({ goals_min: '0', hits_isnull: 'false' });
  expect(router.currentRoute.value.query.page).toBeUndefined();
  await app.get('[aria-label="Sort by Goals"]').trigger('click');
  await flushPromises();
  await app.get('[aria-label="Team contribution pages"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({
    page: '2',
    ordering: '-goals',
    goals_min: '0',
    hits_isnull: 'false',
  });
});
it('keeps confirmed metadata visible when contributions fail and recovers to page one', async () => {
  let fail = true;
  mockApi((url) =>
    fail && url.pathname.endsWith('/players/')
      ? json({ error: { code: 'not_found', message: 'private detail', fields: {} } }, 404)
      : response(url),
  );
  const { app, router } = await render('/teams/7?season_id=20262027&page=3');
  expect(app.get('h1').text()).toBe('Buffalo Sabres');
  expect(app.get('[role="alert"]').text()).toContain('Team metadata remains available');
  expect(app.text()).not.toContain('private detail');
  fail = false;
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.page).toBe('1');
  expect(app.find('tbody').exists()).toBe(true);
});
it('rejects invalid identities and team filters before reads with explicit recovery', async () => {
  const fetch = mockApi();
  const { app, router } = await render('/teams/0');
  expect(fetch).not.toHaveBeenCalled();
  expect(app.text()).toContain('Team not found');
  await router.push('/teams/7?team=MTL');
  await flushPromises();
  expect(fetch).not.toHaveBeenCalled();
  await app.get('[role="alert"] button:last-child').trigger('click');
  await flushPromises();
  expect(app.get('h1').text()).toBe('Buffalo Sabres');
});
it('clears directory rows on an error and retries without exposing upstream details', async () => {
  let fail = false;
  mockApi((url) =>
    fail
      ? json({ error: { code: 'unavailable', message: 'private detail', fields: {} } }, 503)
      : response(url),
  );
  const { app, router } = await render('/teams');
  fail = true;
  await router.push('/teams?search=BUF');
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.text()).not.toContain('Historical Team');
  expect(app.text()).not.toContain('private detail');
  fail = false;
  await app.get('[role="alert"] button:first-child').trigger('click');
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(true);
});
it('discards late team contributions when navigating to another identity', async () => {
  let resolveOld!: (response: Response) => void;
  mockApi((url) =>
    url.pathname === '/api/v1/teams/7/players/'
      ? new Promise((resolve) => {
          resolveOld = resolve;
        })
      : url.pathname === '/api/v1/teams/27/players/'
        ? json(
            teamPlayers(url.searchParams, {
              results: [{ ...teamPlayers().results[0]!, name: 'Historical Skater' }],
            }),
          )
        : url.pathname === '/api/v1/teams/27/'
          ? json(
              teamDetail(url.searchParams, {
                team: { ...teamDetail().team, nhl_id: 27, name: 'Historical Team' },
              }),
            )
          : response(url),
  );
  const { app, router } = await render();
  await router.push('/teams/27?season_id=20262027');
  await flushPromises();
  resolveOld(json(teamPlayers()));
  await flushPromises();
  expect(app.get('h1').text()).toBe('Historical Team');
  expect(app.get('tbody').text()).toContain('Historical Skater');
  expect(app.get('tbody').text()).not.toContain('Traded Skater');
});
it('bounds a stalled contribution request without hiding confirmed metadata', async () => {
  vi.useFakeTimers();
  mockApi((url, init) =>
    url.pathname.endsWith('/players/')
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
  expect(app.get('h1').text()).toBe('Buffalo Sabres');
  expect(app.get('[role="alert"]').text()).toContain('Unable to load this team contribution page');
});
