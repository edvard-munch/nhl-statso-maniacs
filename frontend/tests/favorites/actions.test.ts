import { afterEach, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { createSession } from '../../src/auth/session.js';
import { createFavoriteActions, type FavoriteActions } from '../../src/favorites/actions.js';
import type { Session } from '../../src/auth/session.js';
import { favorites } from '../fixtures/favorites.js';
const resources: { session: Session; actions: FavoriteActions }[] = [];
afterEach(() => {
  resources.splice(0).forEach(({ session, actions }) => {
    actions.dispose();
    session.dispose();
  });
  vi.useRealTimers();
});
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'action-test' },
  });
async function fixture() {
  const server = {
    user: { id: 1, username: 'First' },
    token: 'initial',
    members: new Set<string>(),
    mode: 'ok',
    incomplete: false,
    readFail: false,
    authFail: false,
    writes: 0,
    reads: 0,
  };
  const calls: {
    path: string;
    method: string;
    query: string;
    headers: Headers;
    body: BodyInit | null | undefined;
  }[] = [];
  const quota = () => ({
    limit: 100,
    skaters_count: [...server.members].filter((key) => key.startsWith('skater:')).length,
    goalies_count: [...server.members].filter((key) => key.startsWith('goalie:')).length,
    total_count: server.members.size,
    remaining: Math.max(0, 100 - server.members.size),
    over_limit: server.members.size > 100,
  });
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = new URL(String(input));
    const method = init?.method || 'GET';
    calls.push({
      path: url.pathname,
      method,
      query: url.search,
      headers: new Headers(init?.headers),
      body: init?.body,
    });
    if (url.pathname.endsWith('/csrf/')) return json({ csrf_token: server.token });
    if (url.pathname.endsWith('/session/')) {
      if (server.authFail) throw new TypeError('Unavailable');
      return json({ authenticated: true, user: server.user });
    }
    if (url.pathname === '/api/v1/me/favorites/') {
      server.reads += 1;
      if (server.readFail) throw new TypeError('private read detail');
      const type = url.searchParams.get('player_type')!;
      const base = favorites().results[0]!;
      const rows = [...server.members]
        .filter((key) => key.startsWith(`${type}:`))
        .map((key) => ({ ...base, player_type: type, nhl_id: Number(key.split(':')[1]) }));
      return json({
        ...favorites(url.searchParams),
        count: server.incomplete ? 101 : rows.length,
        results: rows,
        next: server.incomplete ? 'https://not-followed.example/next' : null,
      });
    }
    server.writes += 1;
    const parts = url.pathname.split('/');
    const type = parts[parts.length - 3]!;
    const id = Number(parts[parts.length - 2]);
    const key = `${type}:${id}`;
    if (server.mode === 'csrf') {
      server.token = 'fresh-token';
      return json({ error: { code: 'csrf_failed', message: 'private detail' } }, 403);
    }
    if (server.mode === 'quota')
      return json({ error: { code: 'favorites_quota_exceeded', message: 'private detail' } }, 409);
    if (server.mode === 'lost-before') throw new TypeError('private network detail');
    const existed = server.members.has(key);
    if (method === 'PUT') server.members.add(key);
    else server.members.delete(key);
    if (server.mode === 'lost-switch') {
      server.user = { id: 2, username: 'Second' };
      throw new TypeError('Response lost');
    }
    if (server.mode === 'lost-after') throw new TypeError('private network detail');
    if (server.mode === 'timeout')
      return new Promise<Response>((_resolve, reject) =>
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        ),
      );
    if (server.mode === 'wrong-shape')
      return json({ is_favorite: true, player_type: type, nhl_id: id + 1, quota: quota() });
    if (method === 'DELETE') return new Response(null, { status: 204 });
    return json(
      { is_favorite: true, player_type: type, nhl_id: id, quota: quota() },
      existed ? 200 : 201,
    );
  });
  const session = createSession({ origin: 'https://nhl.test', fetch });
  await session.checkSession();
  const actions = createFavoriteActions(session);
  resources.push({ session, actions });
  const run = (action: 'add' | 'remove' = 'add', type = 'skater') =>
    actions.run(action, type, 8480001, 'Saved Player', '/favorites?season_id=20262027');
  return { session, actions, server, calls, run };
}
it('verifies identity/CSRF before a query-free explicit PUT and accepts 201 or idempotent 200', async () => {
  const { server, actions, run, calls } = await fixture();
  expect(await run()).toBe(true);
  expect(actions.notice.value?.outcome).toBe('confirmed');
  expect(actions.notice.value?.message).toContain('was added');
  const write = calls.find((call) => call.method === 'PUT')!;
  expect(write.query).toBe('');
  expect(write.body).toBeUndefined();
  expect(write.headers.get('X-CSRFToken')).toBe('initial');
  expect(await run()).toBe(true);
  expect(actions.notice.value?.message).toContain('already saved');
  expect(server.members.size).toBe(1);
});
it('removes explicit typed membership without touching the same ID in the other type', async () => {
  const { server, actions, run } = await fixture();
  server.members.add('skater:8480001');
  server.members.add('goalie:8480001');
  expect(await run('remove')).toBe(true);
  expect(server.members.has('goalie:8480001')).toBe(true);
  expect(server.members.has('skater:8480001')).toBe(false);
  expect(actions.notice.value?.message).toContain('was removed');
  expect(await run('remove')).toBe(true);
});
it('does not disable an already-saved PUT based on a full quota and handles a server quota rejection', async () => {
  const { server, actions, run } = await fixture();
  server.members.add('skater:8480001');
  for (let i = 1; i < 100; i++) server.members.add(`skater:${i}`);
  expect(await run()).toBe(true);
  expect(actions.notice.value?.quota?.remaining).toBe(0);
  server.mode = 'quota';
  expect(await run()).toBe(false);
  expect(actions.notice.value?.message).toContain('Favorites limit');
  expect(server.reads).toBe(0);
});
it('refreshes a rejected CSRF token without repeating the write', async () => {
  const { server, actions, session, run } = await fixture();
  server.mode = 'csrf';
  expect(await run()).toBe(false);
  expect(server.writes).toBe(1);
  expect(server.reads).toBe(0);
  expect(session.client.getCsrfToken()).toBe('fresh-token');
  expect(actions.notice.value?.outcome).toBe('rejected');
  expect(actions.notice.value?.message).not.toContain('private detail');
});
it.each(['add', 'remove'] as const)(
  'observes saved state after a lost %s response without replaying it',
  async (action) => {
    const { server, actions, run, calls } = await fixture();
    if (action === 'remove') server.members.add('skater:8480001');
    server.mode = 'lost-after';
    expect(await run(action)).toBe(true);
    expect(server.writes).toBe(1);
    expect(server.reads).toBe(1);
    expect(actions.notice.value?.outcome).toBe('observed');
    expect(actions.notice.value?.message).toContain('original');
    const read = calls.find((call) => call.path === '/api/v1/me/favorites/')!;
    expect(new URLSearchParams(read.query).get('player_type')).toBe('skater');
    expect(new URLSearchParams(read.query).has('season_id')).toBe(false);
    expect(new URLSearchParams(read.query).has('search')).toBe(false);
  },
);
it('does not claim completion when a complete read disagrees with the intended state', async () => {
  const { server, actions, run } = await fixture();
  server.mode = 'lost-before';
  expect(await run()).toBe(false);
  expect(server.writes).toBe(1);
  expect(actions.notice.value?.outcome).toBe('uncertain');
  expect(actions.notice.value?.desiredObserved).toBe(false);
});
it('never infers absence from an incomplete legacy over-limit read or follows its next URL', async () => {
  const { server, actions, run } = await fixture();
  server.members.add('skater:8480001');
  server.mode = 'lost-after';
  server.incomplete = true;
  expect(await run('remove')).toBe(false);
  expect(server.writes).toBe(1);
  expect(server.reads).toBe(1);
  expect(actions.notice.value?.outcome).toBe('uncertain');
});
it('keeps failed readback uncertain instead of inventing membership', async () => {
  const { server, actions, run } = await fixture();
  server.mode = 'lost-after';
  server.readFail = true;
  expect(await run()).toBe(false);
  expect(server.writes).toBe(1);
  expect(actions.notice.value?.message).toContain('could not be confirmed');
  expect(actions.notice.value?.message).not.toContain('private read detail');
});
it('treats a mismatched successful body as uncertain and checks current membership', async () => {
  const { server, actions, run } = await fixture();
  server.mode = 'wrong-shape';
  expect(await run()).toBe(true);
  expect(actions.notice.value?.outcome).toBe('observed');
  expect(server.writes).toBe(1);
});
it('refuses a write when cookie identity changed before the initial verification', async () => {
  const { server, session, actions, run } = await fixture();
  server.user = { id: 2, username: 'Second' };
  expect(await run()).toBe(false);
  expect(server.writes).toBe(0);
  expect(session.user.value?.id).toBe(2);
  expect(actions.notice.value).toBeNull();
});
it('serializes private writes with auth actions and bounds a timed-out write before readback', async () => {
  vi.useFakeTimers();
  const { server, session, actions, run } = await fixture();
  server.mode = 'timeout';
  const pending = run();
  await flushPromises();
  expect(server.writes).toBe(1);
  expect(await run()).toBe(false);
  expect(await session.logout()).toBe(false);
  await vi.advanceTimersByTimeAsync(10_000);
  await flushPromises();
  expect(await pending).toBe(true);
  expect(server.writes).toBe(1);
  expect(actions.notice.value?.outcome).toBe('observed');
});
it('clears notices on account revision changes and never publishes after disposal', async () => {
  const { session, actions, run } = await fixture();
  await run();
  expect(actions.notice.value).not.toBeNull();
  await session.checkSession();
  expect(actions.notice.value).toBeNull();
  actions.dispose();
  expect(await run()).toBe(false);
});

it('does not send a private write when initial session verification fails', async () => {
  const { server, session, actions, run } = await fixture();
  server.authFail = true;
  expect(await run()).toBe(false);
  expect(server.writes).toBe(0);
  expect(session.status.value).toBe('error');
  expect(actions.notice.value).toBeNull();
});
it('does not read or publish old-account membership after uncertainty reveals another account', async () => {
  const { server, session, actions, run } = await fixture();
  server.mode = 'lost-switch';
  expect(await run()).toBe(false);
  expect(server.writes).toBe(1);
  expect(server.reads).toBe(0);
  expect(session.user.value?.id).toBe(2);
  expect(actions.notice.value).toBeNull();
});
it('cancels pending client work on app disposal without publishing a late outcome or replaying', async () => {
  const { server, session, actions, run } = await fixture();
  server.mode = 'timeout';
  const pending = run();
  await flushPromises();
  expect(server.writes).toBe(1);
  actions.dispose();
  session.dispose();
  expect(await pending).toBe(false);
  expect(server.reads).toBe(0);
  expect(actions.notice.value).toBeNull();
});
