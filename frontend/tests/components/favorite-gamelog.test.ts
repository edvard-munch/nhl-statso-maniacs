// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { createSession, sessionKey } from '../../src/auth/session.js';
import type { SessionUser } from '../../src/api/index.js';
import { favoriteGamelog } from '../fixtures/favorite-gamelog.js';
import { favorites } from '../fixtures/favorites.js';
import { profile, seasonHistory } from '../fixtures/profile.js';
import { gamelogGameDetail } from '../fixtures/gamelog.js';
let wrapper: VueWrapper | undefined;
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'favorite-log-test' },
  });
type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;
async function render(
  path = '/favorites/gamelog',
  options: { anonymous?: boolean; bootstrap?: boolean; read?: Handler } = {},
) {
  const server = {
    user: options.anonymous ? null : ({ id: 1, username: 'First' } as SessionUser | null),
    failSession: false,
  };
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/csrf/')) return json({ csrf_token: 'fixture-token' });
    if (url.pathname.endsWith('/session/')) {
      if (server.failSession) throw new TypeError('private session detail');
      return json({ authenticated: !!server.user, user: server.user });
    }
    if (url.pathname.endsWith('/login/')) {
      const body = JSON.parse(String(init?.body));
      server.user = { id: body.username === 'Second' ? 2 : 1, username: body.username };
      return json({ authenticated: true, user: server.user, csrf_token: 'login-token' });
    }
    if (url.pathname.endsWith('/logout/')) {
      server.user = null;
      return json({ authenticated: false, user: null, csrf_token: 'logout-token' });
    }
    if (url.pathname === '/api/v1/me/favorites/gamelog/')
      return options.read
        ? options.read(url, init)
        : json(favoriteGamelog(url.searchParams, server.user?.username));
    if (url.pathname === '/api/v1/me/favorites/')
      return json(favorites(url.searchParams, server.user?.username));
    if (url.pathname.startsWith('/api/v1/games/')) return json(gamelogGameDetail());
    if (url.pathname.endsWith('/seasons/')) return json(seasonHistory(url.searchParams));
    return json(profile(url.searchParams));
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
  const reads = () =>
    fetch.mock.calls.filter(
      ([input]) => new URL(String(input)).pathname === '/api/v1/me/favorites/gamelog/',
    );
  return { app: wrapper, router, session, server, fetch, reads };
}
beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()));
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
it('gates unknown/anonymous sessions and preserves the exact log through sign-in', async () => {
  const context = '/favorites/gamelog?ordering=player_name,-date&page=2';
  const { app, router, session, reads } = await render(context, {
    anonymous: true,
    bootstrap: false,
  });
  expect(reads()).toHaveLength(0);
  await session.checkSession();
  await flushPromises();
  expect(reads()).toHaveLength(0);
  await app
    .findAll('main a')
    .find((link) => link.text() === 'Sign in to view Favorites gamelog')!
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
it('retains two favorite rows in one game and explicit orphan/undated evidence with actual PP/SH TOI', async () => {
  const { app, router, reads } = await render();
  expect(app.findAll('tbody tr')).toHaveLength(4);
  expect(app.text()).toContain('All saved seasons and dates');
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
  expect(app.text()).toContain('12:34');
  expect(app.text()).toContain('00:00');
  expect(app.text()).toContain('01:35');
  expect(
    app.findAll('tbody a').filter((link) => link.text().includes('Game 2026020001')),
  ).toHaveLength(2);
  const orphan = app.findAll('tbody tr')[2]!;
  expect(orphan.text()).toContain('Unverified');
  expect(orphan.findAll('a')).toHaveLength(1);
  expect(
    orphan
      .findAll('td')
      .slice(9)
      .every((cell) => cell.text() === '—'),
  ).toBe(true);
  expect(app.text()).toContain('Date unavailable');
  expect(app.get('[aria-label="Favorites gamelog quota"]').text()).toContain('5 of 100');
  expect(new URL(String(reads()[0]![0])).searchParams.has('season_id')).toBe(false);
});
it('preserves list/game/profile context and excludes it from private/public API queries', async () => {
  const list = '/favorites?season_id=20262027&mode=averages&page=2';
  const log =
    '/favorites/gamelog?player_type=skater&ordering=player_name,-date&page=2&returnTo=' +
    encodeURIComponent(list);
  const { app, router, fetch } = await render(log);
  await app
    .findAll('tbody a')
    .find((link) => link.text().includes('Game 2026020001'))!
    .trigger('click');
  await flushPromises();
  expect(app.get('main a').text()).toBe('Back to Favorites gamelog');
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(log);
  await app.get('tbody a').trigger('click');
  await flushPromises();
  expect(app.get('main a').text()).toBe('Back to Favorites gamelog');
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(log);
  await app.get('main a').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe(list);
  const urls = fetch.mock.calls.map(([input]) => new URL(String(input)));
  expect(
    urls
      .filter((url) => url.pathname.endsWith('/favorites/gamelog/'))
      .every((url) => !url.searchParams.has('returnTo')),
  ).toBe(true);
  expect(urls.filter((url) => url.pathname.includes('/games/')).every((url) => !url.search)).toBe(
    true,
  );
});
it('offers selected-season and all-saved entries without copying list statistic filters', async () => {
  const { app, router } = await render('/favorites?season_id=20262027&mode=averages&goals_min=0.5');
  await app
    .findAll('main a')
    .find((link) => link.text() === 'Selected-season Favorites game log')!
    .trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBe('20262027');
  expect(router.currentRoute.value.query.mode).toBeUndefined();
  expect(router.currentRoute.value.query.goals_min).toBeUndefined();
  await app.get('main a').trigger('click');
  await flushPromises();
  await app
    .findAll('main a')
    .find((link) => link.text() === 'All saved Favorite games')!
    .trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.season_id).toBeUndefined();
});
it('passes global name ordering, literal search, zero/false filters and paging to the scoped API', async () => {
  const { app, router } = await render('/favorites/gamelog?ordering=player_name,-date', {
    read: (url) =>
      json(
        favoriteGamelog(url.searchParams, 'First', {
          count: 250,
          next: 'https://not-followed.example/next',
        }),
      ),
  });
  await app.get('input[type="search"]').setValue('%_Name');
  await app.get('[aria-label="PP TOI (seconds) minimum"]').setValue('0');
  await app.get('[aria-label="Hits availability"]').setValue('false');
  await app.get('form').trigger('submit');
  await flushPromises();
  await app.get('[aria-label="Favorites gamelog pages"] button:last-child').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query).toMatchObject({
    page: '2',
    search: '%_Name',
    ordering: 'player_name,-date',
    pp_toi_seconds_min: '0',
    hits_isnull: 'false',
  });
  expect(app.text()).toContain('250 saved player-game rows');
});
it('rejects mode/owner/wrong-type query state before private reads and clears safely', async () => {
  const { app, reads } = await render('/favorites/gamelog?owner_id=2');
  expect(reads()).toHaveLength(0);
  await app
    .findAll('main button')
    .find((button) => button.text() === 'Clear filters')!
    .trigger('click');
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
});
it('keeps explicit empty seasons and nonzero quota without inventing missing game rows', async () => {
  const { app, router } = await render('/favorites/gamelog?season_id=20272028', {
    read: (url) => json(favoriteGamelog(url.searchParams, 'First', { count: 0, results: [] })),
  });
  expect(router.currentRoute.value.query.season_id).toBe('20272028');
  expect(app.text()).toContain('Players without game rows remain in Favorites');
  expect(app.text()).not.toContain('No saved Favorites yet');
  expect(app.get('[aria-label="Favorites gamelog quota"]').text()).toContain('5 of 100');
});
it('clears old names/rows/quota on logout and never restores a late old-account result', async () => {
  let finish!: (value: Response) => void;
  const { app, session } = await render(undefined, {
    read: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  await session.logout();
  await flushPromises();
  finish(json(favoriteGamelog()));
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.text()).not.toContain('First Saved Player');
  expect(app.find('[aria-label="Favorites gamelog quota"]').exists()).toBe(false);
});
it('discards late rows from a previous account even on the same URL and typed group', async () => {
  let finish!: (value: Response) => void;
  let owner = 'First';
  const { app, session } = await render(undefined, {
    read: (url) =>
      owner === 'First'
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : json(favoriteGamelog(url.searchParams, owner)),
  });
  owner = 'Second';
  await session.login({ username: 'Second', password: 'fixture-password' });
  await flushPromises();
  finish(json(favoriteGamelog()));
  await flushPromises();
  expect(app.text()).toContain('Second Saved Player');
  expect(app.text()).not.toContain('First Saved Player');
});
it('handles authorization expiry explicitly without repeating private reads automatically', async () => {
  const { app, server, reads } = await render(undefined, {
    read: () =>
      json({ error: { code: 'authentication_required', message: 'private auth detail' } }, 403),
  });
  expect(reads()).toHaveLength(1);
  expect(app.text()).not.toContain('private auth detail');
  server.user = null;
  await app.get('main button').trigger('click');
  await flushPromises();
  expect(reads()).toHaveLength(1);
  expect(app.text()).toContain('Sign in to view your Favorites game log');
});
it('keeps goalie fields and decision separate and clears incompatible skater filters', async () => {
  const { app, router } = await render('/favorites/gamelog?goals_min=1');
  await app.findAll('select')[0]!.setValue('goalie');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.query.goals_min).toBeUndefined();
  expect(app.text()).toContain('90.6%');
  expect(app.find('[aria-label="Sort by Goals"]').exists()).toBe(false);
  expect(app.find('[aria-label="Sort by Decision"]').exists()).toBe(true);
});
it('clears old rows after page errors and retries the same page', async () => {
  let fail = false;
  const { app, router } = await render(undefined, {
    read: (url) =>
      fail
        ? json({ error: { code: 'not_found', message: 'private detail' } }, 404)
        : json(favoriteGamelog(url.searchParams)),
  });
  fail = true;
  await router.push('/favorites/gamelog?page=2');
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.text()).not.toContain('First Saved Player');
  expect(app.text()).not.toContain('private detail');
  fail = false;
  await app
    .findAll('main button')
    .find((button) => button.text() === 'Try again')!
    .trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.query.page).toBe('2');
  expect(app.text()).toContain('First Saved Player');
});
it('uses the shared private deadline and keeps read retries explicit', async () => {
  vi.useFakeTimers();
  let fail = true;
  const { app } = await render(undefined, {
    read: (url, init) =>
      fail
        ? new Promise((_resolve, reject) =>
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            ),
          )
        : json(favoriteGamelog(url.searchParams)),
  });
  await vi.advanceTimersByTimeAsync(10_000);
  await flushPromises();
  expect(app.text()).toContain('Unable to load saved Favorites game rows');
  fail = false;
  await app
    .findAll('main button')
    .find((button) => button.text() === 'Try again')!
    .trigger('click');
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
});

it('purges accepted names/quota while session discovery is unavailable and recovers after a verified check', async () => {
  const { app, session, server, reads } = await render();
  const count = reads().length;
  server.failSession = true;
  await session.checkSession();
  await flushPromises();
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.text()).not.toContain('First Saved Player');
  expect(app.find('[aria-label="Favorites gamelog quota"]').exists()).toBe(false);
  expect(reads()).toHaveLength(count);
  server.failSession = false;
  await session.checkSession();
  await flushPromises();
  expect(app.text()).toContain('First Saved Player');
});
