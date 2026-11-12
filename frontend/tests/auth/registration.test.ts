import { afterEach, expect, it, vi } from 'vitest';
import { createSession, AUTH_REQUEST_TIMEOUT_MS, type Session } from '../../src/auth/session.js';
import type { SessionUser } from '../../src/api/index.js';
import { registration } from '../fixtures/registration.js';

const sessions: Session[] = [];
afterEach(() => {
  sessions.splice(0).forEach((session) => session.dispose());
  vi.useRealTimers();
});
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'register-reference' },
  });
const CREATED = { user: { id: 42, username: 'new-user' }, login_required: true };
function fixture() {
  const server = { user: null as SessionUser | null, token: 'current-token' };
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const path = new URL(String(input)).pathname;
    if (path.endsWith('/csrf/')) return json({ csrf_token: server.token });
    if (path.endsWith('/session/'))
      return json({ authenticated: !!server.user, user: server.user });
    return json(CREATED, 201);
  });
  const session = createSession({ origin: 'https://nhl.test', fetch });
  sessions.push(session);
  return { session, server, fetch };
}
const posts = (fetch: ReturnType<typeof fixture>['fetch']) =>
  fetch.mock.calls.filter(([, init]) => init?.method === 'POST');

it('submits exactly four generated fields with CSRF, preserves password whitespace and requires explicit login', async () => {
  const { session, fetch } = fixture();
  const credentials = registration();
  expect(await session.register(credentials)).toEqual(CREATED);
  expect(posts(fetch)).toHaveLength(1);
  const [url, init] = posts(fetch)[0]!;
  expect(String(url)).toBe('https://nhl.test/api/v1/auth/register/');
  expect(JSON.parse(String(init?.body))).toEqual(credentials);
  expect(new Headers(init?.headers).get('X-CSRFToken')).toBe('current-token');
  expect(init?.credentials).toBe('same-origin');
  expect(session.user.value).toBeNull();
  expect(session.client.getCsrfToken()).toBe('current-token');
  expect(fetch.mock.calls.some(([input]) => String(input).endsWith('/login/'))).toBe(false);
});

it('keeps an existing authenticated identity, revision and CSRF token after creating a different account', async () => {
  const { session, server } = fixture();
  server.user = { id: 7, username: 'existing' };
  await session.checkSession();
  const revision = session.revision.value;
  expect((await session.register(registration()))?.user.id).toBe(42);
  expect(session.user.value).toEqual({ id: 7, username: 'existing' });
  expect(session.revision.value).toBe(revision);
  expect(session.client.getCsrfToken()).toBe('current-token');
});

it('shows allowed field/non-field validation errors without changing the caller session', async () => {
  const { session, server, fetch } = fixture();
  server.user = { id: 7, username: 'existing' };
  await session.checkSession();
  fetch.mockImplementationOnce(async () =>
    json(
      {
        error: {
          code: 'invalid_parameters',
          message: 'Invalid fields.',
          fields: {
            username: ['Already exists.'],
            email: ['Invalid email.'],
            password2: ['Passwords do not match.'],
            non_field_errors: ['Check these details.'],
            staff: ['Ignore.'],
            password1: [42, 'Too short.'],
          },
        },
      },
      400,
    ),
  );
  expect(await session.register(registration())).toBeNull();
  expect(session.issue.value?.fields).toEqual({
    username: ['Already exists.'],
    email: ['Invalid email.'],
    password2: ['Passwords do not match.'],
    non_field_errors: ['Check these details.'],
    password1: ['Too short.'],
  });
  expect(session.issue.value?.reference).toBe('register-reference');
  expect(session.user.value?.id).toBe(7);
  expect(fetch).toHaveBeenCalledTimes(3);
});

it('reconciles CSRF rejection without replaying registration or adopting a new identity', async () => {
  const { session, server, fetch } = fixture();
  await session.checkSession();
  server.token = 'changed-token';
  fetch.mockImplementationOnce(async () =>
    json({ error: { code: 'csrf_failed', message: 'Rejected.' } }, 403),
  );
  expect(await session.register(registration())).toBeNull();
  expect(posts(fetch)).toHaveLength(1);
  expect(session.client.getCsrfToken()).toBe('changed-token');
  expect(session.user.value).toBeNull();
  expect(session.issue.value?.message).toContain('Your session changed');
});

it('treats a lost response as uncertain and only rechecks the original caller session', async () => {
  const { session, server, fetch } = fixture();
  server.user = { id: 7, username: 'existing' };
  await session.checkSession();
  fetch.mockImplementationOnce(async () => {
    throw new TypeError('Response lost after possible creation');
  });
  expect(await session.register(registration())).toBeNull();
  expect(posts(fetch)).toHaveLength(1);
  expect(session.user.value?.id).toBe(7);
  expect(session.issue.value?.message).toContain('Account creation could not be confirmed');
  expect(fetch.mock.calls.slice(-2).map(([input]) => new URL(String(input)).pathname)).toEqual([
    '/api/v1/auth/csrf/',
    '/api/v1/auth/session/',
  ]);
});

it('bounds a stalled registration, reconciles and never automatically repeats it', async () => {
  vi.useFakeTimers();
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(
    (_input, init) =>
      new Promise((_resolve, reject) =>
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        ),
      ),
  );
  const pending = session.register(registration());
  await vi.advanceTimersByTimeAsync(AUTH_REQUEST_TIMEOUT_MS);
  expect(await pending).toBeNull();
  expect(posts(fetch)).toHaveLength(1);
  expect(session.busy.value).toBe(false);
  expect(session.status.value).toBe('ready');
});

it('serializes registration against duplicate creation and other auth actions', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  let finish!: (response: Response) => void;
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const pending = session.register(registration());
  expect(session.activeAction.value).toBe('register');
  expect(await session.register(registration())).toBeNull();
  expect(await session.login({ username: 'existing', password: 'secret' })).toBe(false);
  expect(await session.logout()).toBe(false);
  expect(await session.checkSession()).toBe(false);
  expect(posts(fetch)).toHaveLength(1);
  finish(json(CREATED, 201));
  expect(await pending).toEqual(CREATED);
});

it.each([
  { user: CREATED.user, login_required: false },
  { user: null, login_required: true },
])('rejects malformed creation result instead of treating it as a sign-in: %j', async (value) => {
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () => json(value, 201));
  expect(await session.register(registration())).toBeNull();
  expect(session.user.value).toBeNull();
  expect(posts(fetch)).toHaveLength(1);
  expect(session.issue.value?.message).toContain('could not be confirmed');
});

it('does not claim creation on a non-201 success response', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () => json(CREATED, 202));
  expect(await session.register(registration())).toBeNull();
  expect(session.issue.value?.message).toContain('could not be confirmed');
});

it('ignores a late creation response after app disposal', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  let finish!: (response: Response) => void;
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const pending = session.register(registration());
  session.dispose();
  finish(json(CREATED, 201));
  expect(await pending).toBeNull();
  expect(session.user.value).toBeNull();
  expect(session.client.getCsrfToken()).toBeNull();
});
