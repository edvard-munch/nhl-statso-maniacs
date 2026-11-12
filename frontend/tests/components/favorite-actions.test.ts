// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { createSession, sessionKey } from '../../src/auth/session.js';
import { favorites } from '../fixtures/favorites.js';
import { profile, seasonHistory } from '../fixtures/profile.js';
let wrapper: VueWrapper | undefined;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'ui-action' },
  });
async function render(path = '/players/skater/8480001?season_id=20262027', anonymous = false) {
  const server = {
    user: anonymous ? null : { id: 1, username: 'First' },
    members: new Set(['skater:8480001']),
    mode: 'ok',
    writes: 0,
  };
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/csrf/')) return json({ csrf_token: 'fixture-csrf' });
    if (url.pathname.endsWith('/session/'))
      return json({ authenticated: !!server.user, user: server.user });
    if (url.pathname.endsWith('/logout/')) {
      server.user = null;
      return json({ authenticated: false, user: null, csrf_token: 'logout' });
    }
    const data = favorites(url.searchParams);
    const results = data.results.filter((entry) =>
      server.members.has(`${entry.player_type}:${entry.nhl_id}`),
    );
    const quota = {
      limit: 100,
      skaters_count: server.members.size,
      goalies_count: 0,
      total_count: server.members.size,
      remaining: 100 - server.members.size,
      over_limit: false,
    };
    if (url.pathname === '/api/v1/me/favorites/') {
      if (url.searchParams.get('page') === '2' && !results.length)
        return json({ error: { code: 'not_found', message: 'Page missing' } }, 404);
      return json({ ...data, count: results.length, results, meta: { ...data.meta, quota } });
    }
    if (url.pathname.startsWith('/api/v1/me/favorites/')) {
      server.writes += 1;
      if (server.mode === 'quota')
        return json(
          { error: { code: 'favorites_quota_exceeded', message: 'private detail' } },
          409,
        );
      const key = url.pathname.includes('/goalie/') ? 'goalie:8480001' : 'skater:8480001';
      const existed = server.members.has(key);
      if (init?.method === 'DELETE') server.members.delete(key);
      else server.members.add(key);
      if (server.mode === 'lost') throw new TypeError('private gateway detail');
      if (init?.method === 'DELETE') return new Response(null, { status: 204 });
      return json(
        {
          is_favorite: true,
          player_type: 'skater',
          nhl_id: 8480001,
          quota: {
            ...quota,
            skaters_count: server.members.size,
            total_count: server.members.size,
            remaining: 100 - server.members.size,
          },
        },
        existed ? 200 : 201,
      );
    }
    return json(
      url.pathname.endsWith('/seasons/')
        ? seasonHistory(url.searchParams)
        : profile(url.searchParams),
    );
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
  await session.checkSession();
  await flushPromises();
  return { app: wrapper, session, server, router, fetch };
}
beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()));
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.unstubAllGlobals();
});
it('offers an explicit sign-in entry for anonymous profile saves without sending a write', async () => {
  const { app, server } = await render(undefined, true);
  expect(app.findAll('main a').some((link) => link.text() === 'Sign in to save this player')).toBe(
    true,
  );
  expect(server.writes).toBe(0);
});
it('saves from profiles with isolated private feedback and no optimistic public star state', async () => {
  const { app, server, fetch } = await render();
  server.members.clear();
  await app.get('[aria-label="Save Profile Skater to Favorites"]').trigger('click');
  await flushPromises();
  expect(server.members.has('skater:8480001')).toBe(true);
  expect(server.writes).toBe(1);
  expect(app.get('[aria-label="Favorites action result"]').text()).toContain('was added');
  const write = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')!;
  expect(new URL(String(write[0])).search).toBe('');
  expect(new Headers(write[1]?.headers).get('X-CSRFToken')).toBe('fixture-csrf');
});
it('removes the last favorite and refreshes the authoritative empty state and quota', async () => {
  const { app, server } = await render('/favorites?season_id=20262027');
  await app.get('[aria-label="Remove First Saved Player from Favorites"]').trigger('click');
  await flushPromises();
  expect(server.writes).toBe(1);
  expect(app.text()).toContain('No saved Favorites yet');
  expect(app.get('[aria-label="Favorites quota"]').text()).toContain('0 of 100');
  expect(app.find('tbody').exists()).toBe(false);
  expect(app.get('[aria-label="Favorites action result"]').text()).toContain('was removed');
});
it('returns to the first filtered page only after removal makes the selected page unavailable', async () => {
  const { app, router, server } = await render('/favorites?season_id=20262027&page=2&search=Saved');
  await app.get('[aria-label="Remove First Saved Player from Favorites"]').trigger('click');
  await flushPromises();
  await flushPromises();
  expect(server.writes).toBe(1);
  expect(router.currentRoute.value.query).toMatchObject({
    page: '1',
    search: 'Saved',
    season_id: '20262027',
  });
  expect(app.text()).toContain('No saved Favorites yet');
});
it('keeps quota rejections actionable without claiming success or altering the list', async () => {
  const { app, server } = await render();
  server.mode = 'quota';
  await app.get('[aria-label="Save Profile Skater to Favorites"]').trigger('click');
  await flushPromises();
  expect(server.writes).toBe(1);
  expect(app.get('[aria-label="Favorites action result"]').text()).toContain('Favorites limit');
  expect(app.text()).not.toContain('private detail');
});
it('keeps feedback after row unmount and observes a lost removal without a second DELETE', async () => {
  const { app, server } = await render('/favorites?season_id=20262027');
  server.mode = 'lost';
  await app.get('[aria-label="Remove First Saved Player from Favorites"]').trigger('click');
  await flushPromises();
  expect(server.writes).toBe(1);
  expect(app.text()).toContain('currently absent');
  expect(app.text()).toContain('No saved Favorites yet');
  expect(app.text()).not.toContain('private gateway detail');
});
it('clears private action feedback and quota snapshots after logout', async () => {
  const { app, session } = await render();
  await app.get('[aria-label="Save Profile Skater to Favorites"]').trigger('click');
  await flushPromises();
  expect(app.find('[aria-label="Favorites action result"]').exists()).toBe(true);
  await session.logout();
  await flushPromises();
  expect(app.find('[aria-label="Favorites action result"]').exists()).toBe(false);
});
