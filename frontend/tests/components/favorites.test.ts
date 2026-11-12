// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { createSession, sessionKey } from '../../src/auth/session.js';
import type { SessionUser } from '../../src/api/index.js';
import { favorites } from '../fixtures/favorites.js';
import { profile, seasonHistory } from '../fixtures/profile.js';

let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'favorite-test' },
  });
type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;
async function render(
  path = '/favorites?season_id=20262027',
  options: { anonymous?: boolean; bootstrap?: boolean; privateRead?: Handler } = {},
) {
  const server = {
    user: options.anonymous ? null : ({ id: 1, username: 'First' } as SessionUser | null),
    failSession: false,
    sessionRead: null as (() => Promise<Response>) | null,
  };
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/csrf/')) return json({ csrf_token: 'fixture-token' });
    if (url.pathname.endsWith('/session/')) {
      if (server.failSession) throw new TypeError('private server detail');
      if (server.sessionRead) return server.sessionRead();
      return json({ authenticated: !!server.user, user: server.user });
    }
    if (url.pathname.endsWith('/login/')) {
      const body = JSON.parse(String(init?.body));
      server.user = { id: body.username === 'Second' ? 2 : 1, username: body.username };
      return json({ authenticated: true, user: server.user, csrf_token: 'rotated' });
    }
    if (url.pathname.endsWith('/logout/')) {
      server.user = null;
      return json({ authenticated: false, user: null, csrf_token: 'rotated' });
    }
    if (url.pathname === '/api/v1/me/favorites/')
      return options.privateRead
        ? options.privateRead(url, init)
        : json(favorites(url.searchParams, server.user?.username));
    if (url.pathname.endsWith('/seasons/')) return json(seasonHistory(url.searchParams));
    if (/\/players\/skater\/\d+\/$/.test(url.pathname)) return json(profile(url.searchParams));
    throw new Error(`Unexpected fixture request: ${url.pathname}`);
  });
  vi.stubGlobal('fetch', fetch);
  const session = createSession({ fetch });
  const router = createAppRouter(createMemoryHistory());
  await router.push(path);
  await router.isReady();
  wrapper = mount(App, {
    attachTo: document.body,
    global: { plugins: [router], provide: { [sessionKey as symbol]: session } },
  });
  if (options.bootstrap !== false) await session.checkSession();
  await flushPromises();
  const privateCalls = () =>
    fetch.mock.calls.filter(
      ([input]) => new URL(String(input)).pathname === '/api/v1/me/favorites/',
    );
  return { app: wrapper, router, session, server, fetch, privateCalls };
}
beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()));
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('does not read private data until a healthy signed-in session is known', async () => {
  const { app, session, privateCalls } = await render(undefined, { bootstrap: false });
  expect(privateCalls()).toHaveLength(0);
  expect(app.text()).toContain('Waiting for session checks');
  await session.checkSession();
  await flushPromises();
  expect(privateCalls()).toHaveLength(1);
  expect(app.text()).toContain('First Saved Player');
});
it('keeps anonymous requests gated and returns from explicit sign-in to the full applied query', async () => {
  const context = '/favorites?season_id=20262027&mode=averages&page=2';
  const { app, router, privateCalls } = await render(context, { anonymous: true });
  expect(privateCalls()).toHaveLength(0);
  expect(app.find('tbody').exists()).toBe(false);
  await app
    .findAll('main a')
    .find((link) => link.text() === 'Sign in to view Favorites')!
    .trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.returnTo).toBe(context);
  await app.get('#login-username').setValue('First');
  await app.get('#login-password').setValue('fixture-password');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(context);
  expect(app.text()).toContain('First Saved Player');
});
it('retains missing/unverified/zero-GP members and server quota counts without public facets', async () => {
  const { app, fetch } = await render();
  expect(app.findAll('tbody tr')).toHaveLength(4);
  expect(app.text()).toContain('First Missing Player');
  expect(app.text()).toContain('Unverified');
  const zero = app.findAll('tbody tr').find((row) => row.text().includes('First Zero Player'))!;
  expect(zero.findAll('td')[4]!.text()).toBe('0');
  const missing = app
    .findAll('tbody tr')
    .find((row) => row.text().includes('First Missing Player'))!;
  expect(
    missing
      .findAll('td')
      .slice(4)
      .every((cell) => cell.text() === '—'),
  ).toBe(true);
  expect(app.get('[aria-label="Favorites quota"]').text()).toContain('5 of 100');
  expect(fetch.mock.calls.some(([input]) => String(input).includes('/players/filters/'))).toBe(
    false,
  );
});
it('preserves explicit empty-season saved identities without snapshot fallback', async () => {
  const { app, router } = await render('/favorites?season_id=20272028');
  expect(router.currentRoute.value.query.season_id).toBe('20272028');
  expect(app.findAll('tbody tr')).toHaveLength(4);
  expect(
    app.findAll('tbody tr').every((row) =>
      row
        .findAll('td')
        .slice(4)
        .every((cell) => cell.text() === '—'),
    ),
  ).toBe(true);
  expect(app.get('h2').text()).toContain('2027–28');
});
it('pins a resolved default season only from accepted private data', async () => {
  const { router, app } = await render('/favorites');
  expect(router.currentRoute.value.query.season_id).toBe('20262027');
  expect(app.text()).toContain('First Saved Player');
});
it('clears visible private data during session checks and reloads after verified revision changes', async () => {
  const { app, session, server, privateCalls } = await render();
  let finish!: (value: Response) => void;
  server.sessionRead = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  const calls = privateCalls().length;
  const check = session.checkSession();
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.find('[aria-label="Favorites quota"]').exists()).toBe(false);
  expect(app.text()).not.toContain('First Saved Player');
  expect(privateCalls()).toHaveLength(calls);
  finish(json({ authenticated: true, user: server.user }));
  await check;
  await flushPromises();
  expect(privateCalls().length).toBeGreaterThan(calls);
  expect(app.text()).toContain('First Saved Player');
});
it('clears private rows and quota after logout and suppresses late responses from the old account', async () => {
  let resolveOld!: (response: Response) => void;
  const { app, session } = await render(undefined, {
    privateRead: () =>
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
  });
  await session.logout();
  await flushPromises();
  resolveOld(json(favorites()));
  await flushPromises();
  expect(app.text()).toContain('Sign in to view your saved Favorites');
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.find('[aria-label="Favorites quota"]').exists()).toBe(false);
  expect(app.text()).not.toContain('First Saved Player');
});
it('never accepts a late first-account response after switching to the same route as another account', async () => {
  let resolveOld!: (response: Response) => void;
  let owner = 'First';
  const { app, session } = await render(undefined, {
    privateRead: (url) =>
      owner === 'First'
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : json(favorites(url.searchParams, owner)),
  });
  owner = 'Second';
  await session.login({ username: 'Second', password: 'fixture-password' });
  await flushPromises();
  expect(app.text()).toContain('Second Saved Player');
  resolveOld(json(favorites()));
  await flushPromises();
  expect(app.text()).not.toContain('First Saved Player');
  expect(app.text()).toContain('Second Saved Player');
});
it('purges saved data on an unavailable session and reads nothing until session recovery', async () => {
  const { app, session, server, privateCalls } = await render();
  const calls = privateCalls().length;
  server.failSession = true;
  await session.checkSession();
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.text()).not.toContain('First Saved Player');
  expect(app.text()).toContain('Sign-in status is unavailable');
  expect(privateCalls()).toHaveLength(calls);
  server.failSession = false;
  await session.checkSession();
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
});
it('handles 403 with an explicit session check and no automatic private-read loop', async () => {
  let denied = true;
  const { app, session, server, privateCalls } = await render(undefined, {
    privateRead: (url) =>
      denied
        ? json({ error: { code: 'authentication_required', message: 'private auth detail' } }, 403)
        : json(favorites(url.searchParams)),
  });
  expect(app.text()).toContain('Access to Favorites could not be confirmed');
  expect(app.text()).not.toContain('private auth detail');
  expect(privateCalls()).toHaveLength(1);
  server.user = null;
  await app.get('main button').trigger('click');
  await flushPromises();
  expect(privateCalls()).toHaveLength(1);
  expect(app.text()).toContain('Sign in to view your saved Favorites');
  denied = false;
  await session.login({ username: 'First', password: 'fixture-password' });
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
});
it('uses private query filtering, zero/false values and URL paging without recomputing quota', async () => {
  const { app, router } = await render(undefined, {
    privateRead: (url) =>
      json(
        favorites(url.searchParams, 'First', {
          count: 101,
          next: 'https://not-followed.example/page',
        }),
      ),
  });
  await app.get('[aria-label="Goals minimum"]').setValue('0');
  await app.get('[aria-label="Hits availability"]').setValue('false');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({ goals_min: '0', hits_isnull: 'false' });
  expect(router.currentRoute.value.query.page).toBeUndefined();
  await app.get('[aria-label="Sort by Goals"]').trigger('click');
  await flushPromises();
  await app.get('[aria-label="Favorites pages"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({
    page: '2',
    ordering: '-goals',
    goals_min: '0',
    hits_isnull: 'false',
  });
  expect(app.get('[aria-label="Favorites quota"]').text()).toContain('5 of 100');
});
it('opens public profiles with private return context and gates that return after logout', async () => {
  const context = '/favorites?season_id=20262027&mode=averages&page=2';
  const { app, router, session, privateCalls } = await render(context);
  await app.get('tbody a').trigger('click');
  await flushPromises();
  expect(app.get('h1').text()).toBe('Profile Skater');
  expect(app.get('main a').text()).toBe('Back to Favorites');
  await session.logout();
  await flushPromises();
  const calls = privateCalls().length;
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(context);
  expect(privateCalls()).toHaveLength(calls);
  expect(app.find('tbody').exists()).toBe(false);
});
it('keeps private filters invalid before reads and supports safe clear-filter recovery', async () => {
  const { app, privateCalls } = await render('/favorites?owner_id=2');
  expect(privateCalls()).toHaveLength(0);
  expect(app.text()).toContain('unsupported');
  await app.get('main button').trigger('click');
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
});
it('clears previous rows on page errors and retries the selected private page explicitly', async () => {
  let fail = false;
  const { app, router } = await render(undefined, {
    privateRead: (url) =>
      fail
        ? json({ error: { code: 'not_found', message: 'private server detail' } }, 404)
        : json(favorites(url.searchParams)),
  });
  fail = true;
  await router.push('/favorites?season_id=20262027&page=2');
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.text()).not.toContain('First Saved Player');
  expect(app.text()).not.toContain('private server detail');
  fail = false;
  await app.get('main button').trigger('click');
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
  expect(router.currentRoute.value.query.page).toBe('2');
});
it('switches private goalie contracts, with rates and no skater averages', async () => {
  const { app, router } = await render('/favorites?season_id=20262027&mode=averages&goals_min=0.5');
  await app.findAll('select')[0]!.setValue('goalie');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({ player_type: 'goalie', mode: 'totals' });
  expect(router.currentRoute.value.query.goals_min).toBeUndefined();
  expect(app.get('tbody').text()).toContain('91.5%');
  expect(app.find('[aria-label="Sort by Goals"]').exists()).toBe(false);
});
it('bounds a stalled private read and retries GET without sending writes', async () => {
  vi.useFakeTimers();
  let fail = true;
  const { app, privateCalls } = await render(undefined, {
    privateRead: (url, init) =>
      fail
        ? new Promise((_resolve, reject) =>
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            ),
          )
        : json(favorites(url.searchParams)),
  });
  await vi.advanceTimersByTimeAsync(10_000);
  await flushPromises();
  expect(app.text()).toContain('Unable to load saved Favorites');
  fail = false;
  await app.get('main button').trigger('click');
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
  expect(privateCalls().every(([, init]) => init?.method === 'GET')).toBe(true);
});

it('retains saved identities with null global season and distinguishes empty lists from empty filtered groups', async () => {
  let groupEmpty = false;
  let listEmpty = false;
  const { app } = await render('/favorites', {
    privateRead: (url) => {
      const data = favorites(url.searchParams);
      return json({
        ...data,
        count: groupEmpty ? 0 : data.count,
        results: groupEmpty
          ? []
          : data.results.map((entry) => ({
              ...entry,
              stats: null,
              availability: 'missing',
              teams: [],
            })),
        meta: {
          ...data.meta,
          season_id: null,
          quota: listEmpty
            ? {
                limit: 100,
                skaters_count: 0,
                goalies_count: 0,
                total_count: 0,
                remaining: 100,
                over_limit: false,
              }
            : data.meta.quota,
        },
      });
    },
  });
  expect(app.get('h2').text()).toContain('No loaded season');
  expect(app.text()).toContain('First Saved Player');
  groupEmpty = true;
  await app
    .findAll('main button')
    .find((button) => button.text() === 'Refresh Favorites')!
    .trigger('click');
  await flushPromises();
  expect(app.text()).toContain('No Favorites match this type and selection');
  expect(app.text()).not.toContain('No saved Favorites yet');
  listEmpty = true;
  await app
    .findAll('main button')
    .find((button) => button.text() === 'Refresh Favorites')!
    .trigger('click');
  await flushPromises();
  expect(app.text()).toContain('No saved Favorites yet.');
});

it('shows existing over-limit data and uses the server quota without clamping rows or recalculating counts', async () => {
  const { app } = await render(undefined, {
    privateRead: (url) => {
      const data = favorites(url.searchParams);
      return json({
        ...data,
        meta: {
          ...data.meta,
          quota: {
            limit: 100,
            skaters_count: 100,
            goalies_count: 1,
            total_count: 101,
            remaining: 0,
            over_limit: true,
          },
        },
      });
    },
  });
  expect(app.get('[aria-label="Favorites quota"]').text()).toContain('101 of 100');
  expect(app.findAll('tbody tr')).toHaveLength(4);
  expect(app.text()).toContain('Existing entries are retained');
});

it('does not loop when a verified signed-in session still receives a forbidden response', async () => {
  const { app, privateCalls } = await render(undefined, {
    privateRead: () =>
      json({ error: { code: 'authentication_required', message: 'Unavailable' } }, 403),
  });
  expect(privateCalls()).toHaveLength(1);
  await app.get('main button').trigger('click');
  await flushPromises();
  expect(privateCalls()).toHaveLength(2);
  expect(app.text()).toContain('Access to Favorites could not be confirmed');
  expect(app.find('tbody').exists()).toBe(false);
});
