import { afterEach, expect, it, vi } from 'vitest';
import { createSession, AUTH_REQUEST_TIMEOUT_MS, type Session } from '../../src/auth/session.js';
import type { SessionUser } from '../../src/api/index.js';

const sessions: Session[] = [];
afterEach(() => {
  sessions.splice(0).forEach((session) => session.dispose());
  vi.useRealTimers();
});
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'auth-reference' },
  });
function fixture() {
  const server = {
    user: null as SessionUser | null,
    token: 'initial-token',
    fail: false,
    lose: false,
  };
  const calls: Array<{ path: string; init: RequestInit | undefined }> = [];
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const path = new URL(String(input)).pathname;
    calls.push({ path, init });
    if (server.fail) throw new TypeError('Network unavailable');
    if (path.endsWith('/csrf/')) return json({ csrf_token: server.token });
    if (path.endsWith('/session/'))
      return json({ authenticated: !!server.user, user: server.user });
    if (new Headers(init?.headers).get('X-CSRFToken') !== server.token)
      return json({ error: { code: 'csrf_failed', message: 'CSRF failed.' } }, 403);
    if (path.endsWith('/login/')) {
      const body = JSON.parse(String(init?.body));
      if (body.password === 'wrong')
        return json(
          { error: { code: 'invalid_credentials', message: 'Invalid credentials.' } },
          400,
        );
      server.user = { id: body.username === 'second' ? 2 : 1, username: body.username };
      server.token = 'login-token';
    } else {
      server.user = null;
      server.token = 'logout-token';
    }
    if (server.lose) throw new TypeError('Response lost');
    return json({ authenticated: !!server.user, user: server.user, csrf_token: server.token });
  });
  const session = createSession({ origin: 'https://nhl.test', fetch });
  sessions.push(session);
  return { session, fetch, calls, server };
}

it('bootstraps CSRF before session discovery, preserving HttpOnly/session-backed compatibility', async () => {
  const { session, calls } = fixture();
  expect(await session.checkSession()).toBe(true);
  expect(calls.map((call) => call.path)).toEqual(['/api/v1/auth/csrf/', '/api/v1/auth/session/']);
  expect(
    calls.every(
      (call) => call.init?.credentials === 'same-origin' && call.init.redirect === 'error',
    ),
  ).toBe(true);
  expect(session.user.value).toBeNull();
  expect(session.status.value).toBe('ready');
  expect(session.client.getCsrfToken()).toBe('initial-token');
});

it('sends only exact credentials, captures login/logout rotation and invalidates identity revisions', async () => {
  const { session, calls } = fixture();
  await session.checkSession();
  const revision = session.revision.value;
  expect(await session.login({ username: 'first', password: '  exact password  ' })).toBe(true);
  expect(JSON.parse(String(calls[2]!.init?.body))).toEqual({
    username: 'first',
    password: '  exact password  ',
  });
  expect(session.user.value).toEqual({ id: 1, username: 'first' });
  expect(session.revision.value).toBeGreaterThan(revision);
  expect(session.client.getCsrfToken()).toBe('login-token');
  expect(await session.logout()).toBe(true);
  expect(new Headers(calls[3]!.init?.headers).get('X-CSRFToken')).toBe('login-token');
  expect(session.user.value).toBeNull();
  expect(session.client.getCsrfToken()).toBe('logout-token');
});

it('preserves the existing account and token after generic invalid credentials', async () => {
  const { session, server, calls } = fixture();
  server.user = { id: 1, username: 'first' };
  await session.checkSession();
  const revision = session.revision.value;
  expect(await session.login({ username: 'unknown', password: 'wrong' })).toBe(false);
  expect(session.user.value?.id).toBe(1);
  expect(session.revision.value).toBe(revision);
  expect(session.issue.value?.message).toBe('Unable to sign in with those credentials.');
  expect(session.issue.value?.reference).toBe('auth-reference');
  expect(calls).toHaveLength(3);
});

it('switches accounts without retaining the former identity', async () => {
  const { session, server } = fixture();
  server.user = { id: 1, username: 'first' };
  await session.checkSession();
  const revision = session.revision.value;
  await session.login({ username: 'second', password: 'secret' });
  expect(session.user.value).toEqual({ id: 2, username: 'second' });
  expect(session.revision.value).toBeGreaterThan(revision);
});

it('reconciles a CSRF failure and requires a new explicit submit instead of replaying the POST', async () => {
  const { session, server, calls } = fixture();
  await session.checkSession();
  server.token = 'changed-in-another-tab';
  server.user = { id: 2, username: 'second' };
  expect(await session.login({ username: 'first', password: 'secret' })).toBe(false);
  expect(calls.filter((call) => call.init?.method === 'POST')).toHaveLength(1);
  expect(session.user.value?.id).toBe(2);
  expect(session.client.getCsrfToken()).toBe('changed-in-another-tab');
  expect(session.issue.value?.message).toContain('Your session changed');
});

it.each(['login', 'logout'] as const)(
  'rechecks state after a lost %s response without retrying the mutation',
  async (action) => {
    const { session, server, calls } = fixture();
    server.user = action === 'logout' ? { id: 1, username: 'first' } : null;
    await session.checkSession();
    server.lose = true;
    expect(
      await (action === 'login'
        ? session.login({ username: 'first', password: 'secret' })
        : session.logout()),
    ).toBe(false);
    expect(calls.filter((call) => call.init?.method === 'POST')).toHaveLength(1);
    expect(session.status.value).toBe('ready');
    expect(session.user.value?.id ?? null).toBe(action === 'login' ? 1 : null);
    expect(session.client.getCsrfToken()).toBe(action === 'login' ? 'login-token' : 'logout-token');
    expect(session.issue.value?.message).toContain('could not be confirmed');
  },
);

it('treats failed discovery as unknown, clears identity/token, then recovers and handles expired sessions', async () => {
  const { session, server } = fixture();
  server.user = { id: 1, username: 'first' };
  await session.checkSession();
  server.fail = true;
  expect(await session.checkSession()).toBe(false);
  expect(session.status.value).toBe('error');
  expect(session.user.value).toBeNull();
  expect(session.client.getCsrfToken()).toBeNull();
  server.fail = false;
  server.user = null;
  expect(await session.checkSession()).toBe(true);
  expect(session.status.value).toBe('ready');
  expect(session.user.value).toBeNull();
});

it('serializes mutations and prevents duplicate posts while a submit is pending', async () => {
  let finish!: (response: Response) => void;
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith('/csrf/')) return json({ csrf_token: 'initial' });
    if (url.endsWith('/session/')) return json({ authenticated: false, user: null });
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  const session = createSession({ origin: 'https://nhl.test', fetch });
  sessions.push(session);
  await session.checkSession();
  const pending = session.login({ username: 'first', password: 'secret' });
  expect(await session.login({ username: 'second', password: 'secret' })).toBe(false);
  expect(await session.logout()).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(3);
  finish(json({ authenticated: true, user: { id: 1, username: 'first' }, csrf_token: 'rotated' }));
  expect(await pending).toBe(true);
});

it('rejects malformed session/bootstrap responses rather than inventing anonymous state', async () => {
  for (const malformed of [
    { authenticated: true, user: null },
    { authenticated: false, user: {} },
    {},
  ]) {
    const fetch = vi.fn<typeof globalThis.fetch>(async (input) =>
      json(String(input).endsWith('/csrf/') ? { csrf_token: 'initial' } : malformed),
    );
    const session = createSession({ origin: 'https://nhl.test', fetch });
    sessions.push(session);
    expect(await session.checkSession()).toBe(false);
    expect(session.status.value).toBe('error');
    expect(session.client.getCsrfToken()).toBeNull();
  }
});

it('does not publish late identity or captured CSRF after disposal', async () => {
  let finish!: (response: Response) => void;
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) =>
    String(input).endsWith('/csrf/')
      ? json({ csrf_token: 'initial' })
      : new Promise((resolve) => {
          finish = resolve;
        }),
  );
  const session = createSession({ origin: 'https://nhl.test', fetch });
  sessions.push(session);
  const pending = session.checkSession();
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  session.dispose();
  finish(json({ authenticated: true, user: { id: 1, username: 'first' } }));
  expect(await pending).toBe(false);
  expect(session.user.value).toBeNull();
  expect(session.client.getCsrfToken()).toBeNull();
});

it('bounds initial discovery and returns an unknown/error state after a timeout', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn<typeof globalThis.fetch>(
    (_input, init) =>
      new Promise((_resolve, reject) =>
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        ),
      ),
  );
  const session = createSession({ origin: 'https://nhl.test', fetch });
  sessions.push(session);
  const pending = session.checkSession();
  await vi.advanceTimersByTimeAsync(AUTH_REQUEST_TIMEOUT_MS);
  expect(await pending).toBe(false);
  expect(session.status.value).toBe('error');
  expect(session.busy.value).toBe(false);
});

it('exposes only allowed string field errors for invalid parameters', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () =>
    json(
      {
        error: {
          code: 'invalid_parameters',
          message: 'Invalid.',
          fields: {
            username: ['Too long.'],
            password: [42, 'Required.'],
            staff: ['Ignore this field.'],
          },
        },
      },
      400,
    ),
  );
  expect(await session.login({ username: 'first', password: 'secret' })).toBe(false);
  expect(session.issue.value?.fields).toEqual({ username: ['Too long.'], password: ['Required.'] });
});

it('reconciles a timed-out POST that may have succeeded, without replaying it', async () => {
  vi.useFakeTimers();
  const { session, server, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce((_input, init) => {
    server.user = { id: 1, username: 'first' };
    server.token = 'after-timeout';
    return new Promise((_resolve, reject) =>
      init?.signal?.addEventListener('abort', () =>
        reject(new DOMException('Aborted', 'AbortError')),
      ),
    );
  });
  const pending = session.login({ username: 'first', password: 'secret' });
  await vi.advanceTimersByTimeAsync(AUTH_REQUEST_TIMEOUT_MS);
  expect(await pending).toBe(false);
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  expect(session.user.value?.id).toBe(1);
  expect(session.client.getCsrfToken()).toBe('after-timeout');
});

it('requires a rotated token in a successful mutation response and reconciles malformed success', async () => {
  const { session, server, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () => {
    server.user = { id: 1, username: 'first' };
    server.token = 'actual-current-token';
    return json({ authenticated: true, user: server.user });
  });
  expect(await session.login({ username: 'first', password: 'secret' })).toBe(false);
  expect(session.client.getCsrfToken()).toBe('actual-current-token');
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
});

it('keeps a late mutation token isolated after the app session is disposed', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  let finish!: (response: Response) => void;
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const pending = session.login({ username: 'first', password: 'secret' });
  session.dispose();
  finish(
    json({ authenticated: true, user: { id: 1, username: 'first' }, csrf_token: 'late-token' }),
  );
  expect(await pending).toBe(false);
  expect(session.user.value).toBeNull();
  expect(session.client.getCsrfToken()).toBeNull();
});
