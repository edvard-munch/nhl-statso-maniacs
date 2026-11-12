import { afterEach, expect, it, vi } from 'vitest';
import { createSession, AUTH_REQUEST_TIMEOUT_MS, type Session } from '../../src/auth/session.js';
import type { SessionUser } from '../../src/api/index.js';

const sessions: Session[] = [];
afterEach(() => {
  sessions.splice(0).forEach((session) => session.dispose());
  vi.useRealTimers();
});
const LINK = { uidb64: 'MQ', token: 'test-reset-secret' };
const PASSWORDS = {
  new_password1: '  exact new password  ',
  new_password2: '  exact new password  ',
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'recovery-reference' },
  });
function fixture() {
  const server = { user: null as SessionUser | null, token: 'current-csrf', targetIsCaller: false };
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const path = new URL(String(input)).pathname;
    if (path.endsWith('/csrf/')) return json({ csrf_token: server.token });
    if (path.endsWith('/session/'))
      return json({ authenticated: !!server.user, user: server.user });
    if (path.endsWith('/validate/')) return json({ valid: true });
    if (path.endsWith('/confirm/')) {
      if (server.targetIsCaller) server.user = null;
      return json({ password_reset: true, login_required: true });
    }
    return json({ accepted: true });
  });
  const session = createSession({ origin: 'https://nhl.test', fetch });
  sessions.push(session);
  return { session, server, fetch };
}
const posts = (fetch: ReturnType<typeof fixture>['fetch']) =>
  fetch.mock.calls.filter(([, init]) => init?.method === 'POST');

it('requests mail through the generated endpoint without inferring account existence or delivery', async () => {
  const { session, fetch } = fixture();
  expect(await session.requestPasswordReset({ email: 'unknown@example.invalid' })).toEqual({
    accepted: true,
  });
  const [input, init] = posts(fetch)[0]!;
  expect(String(input)).toBe('https://nhl.test/api/v1/auth/password-reset/');
  expect(JSON.parse(String(init?.body))).toEqual({ email: 'unknown@example.invalid' });
  expect(new Headers(init?.headers).get('X-CSRFToken')).toBe('current-csrf');
  expect(session.user.value).toBeNull();
});

it('validates without consuming a link and sends all secrets in JSON, never paths/queries', async () => {
  const { session, fetch } = fixture();
  expect(await session.validatePasswordReset(LINK)).toEqual({ valid: true });
  expect(await session.validatePasswordReset(LINK)).toEqual({ valid: true });
  for (const [input, init] of posts(fetch)) {
    expect(String(input)).toBe('https://nhl.test/api/v1/auth/password-reset/validate/');
    expect(JSON.parse(String(init?.body))).toEqual(LINK);
  }
});

it.each([true, false])(
  'reconciles the current caller after confirmed reset without automatic login (target is caller: %s)',
  async (targetIsCaller) => {
    const { session, server, fetch } = fixture();
    server.user = { id: 7, username: 'caller' };
    server.targetIsCaller = targetIsCaller;
    await session.checkSession();
    expect(await session.confirmPasswordReset({ ...LINK, ...PASSWORDS })).toEqual({
      password_reset: true,
      login_required: true,
    });
    const [input, init] = posts(fetch)[0]!;
    expect(String(input)).toBe('https://nhl.test/api/v1/auth/password-reset/confirm/');
    expect(JSON.parse(String(init?.body))).toEqual({ ...LINK, ...PASSWORDS });
    expect(session.user.value?.id ?? null).toBe(targetIsCaller ? null : 7);
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/login/'))).toBe(false);
    expect(fetch.mock.calls.slice(-2).map(([url]) => new URL(String(url)).pathname)).toEqual([
      '/api/v1/auth/csrf/',
      '/api/v1/auth/session/',
    ]);
  },
);

it('retains known reset success if session rediscovery fails, while clearing uncertain caller state', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () => json({ password_reset: true, login_required: true }));
  fetch.mockImplementationOnce(async () => {
    throw new TypeError('Discovery down');
  });
  expect(await session.confirmPasswordReset({ ...LINK, ...PASSWORDS })).toEqual({
    password_reset: true,
    login_required: true,
  });
  expect(session.status.value).toBe('error');
  expect(session.user.value).toBeNull();
  expect(session.client.getCsrfToken()).toBeNull();
});

it('preserves password field errors without exposing UID/token errors or echoing submitted values', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () =>
    json(
      {
        error: {
          code: 'invalid_parameters',
          message: 'Invalid.',
          fields: {
            new_password2: ['Passwords do not match.'],
            token: ['Do not display.'],
            uidb64: ['Do not display.'],
            new_password1: [42, 'Too short.'],
          },
        },
      },
      400,
    ),
  );
  expect(await session.confirmPasswordReset({ ...LINK, ...PASSWORDS })).toBeNull();
  expect(session.issue.value?.fields).toEqual({
    new_password1: ['Too short.'],
    new_password2: ['Passwords do not match.'],
  });
  expect(session.issue.value?.code).toBe('invalid_parameters');
  expect(posts(fetch)).toHaveLength(1);
});

it('uses one invalid-link error for validation/confirmation and never replays a rejected write', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () =>
    json({ error: { code: 'invalid_reset_token', message: 'Invalid link.' } }, 400),
  );
  expect(await session.confirmPasswordReset({ ...LINK, ...PASSWORDS })).toBeNull();
  expect(session.issue.value?.message).toBe('This reset link is invalid or no longer available.');
  expect(posts(fetch)).toHaveLength(1);
});

it('handles uniform mail unavailability without treating it as an accepted or unknown-account result', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  fetch.mockImplementationOnce(async () =>
    json({ error: { code: 'password_reset_unavailable', message: 'Unavailable.' } }, 503),
  );
  expect(await session.requestPasswordReset({ email: 'unknown@example.invalid' })).toBeNull();
  expect(session.issue.value?.message).toContain('currently unavailable');
});

it('recovers CSRF through reads and requires an explicit new action', async () => {
  const { session, server, fetch } = fixture();
  await session.checkSession();
  server.token = 'rotated-csrf';
  fetch.mockImplementationOnce(async () =>
    json({ error: { code: 'csrf_failed', message: 'Failed.' } }, 403),
  );
  expect(await session.confirmPasswordReset({ ...LINK, ...PASSWORDS })).toBeNull();
  expect(posts(fetch)).toHaveLength(1);
  expect(session.client.getCsrfToken()).toBe('rotated-csrf');
  expect(session.issue.value?.code).toBe('csrf_failed');
});

it.each(['mail', 'confirm'] as const)(
  'does not automatically repeat uncertain %s requests',
  async (action) => {
    const { session, fetch } = fixture();
    await session.checkSession();
    fetch.mockImplementationOnce(async () => {
      throw new TypeError('Response lost');
    });
    expect(
      await (action === 'mail'
        ? session.requestPasswordReset({ email: 'any@example.invalid' })
        : session.confirmPasswordReset({ ...LINK, ...PASSWORDS })),
    ).toBeNull();
    expect(posts(fetch)).toHaveLength(1);
    expect(session.issue.value?.code).toBe('unconfirmed');
  },
);

it('serializes duplicate password-changing requests against other auth actions', async () => {
  const { session, fetch } = fixture();
  await session.checkSession();
  let finish!: (response: Response) => void;
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const pending = session.confirmPasswordReset({ ...LINK, ...PASSWORDS });
  expect(await session.confirmPasswordReset({ ...LINK, ...PASSWORDS })).toBeNull();
  expect(await session.logout()).toBe(false);
  expect(
    await session.register({
      username: 'new',
      email: 'new@example.invalid',
      password1: 'secret',
      password2: 'secret',
    }),
  ).toBeNull();
  finish(json({ password_reset: true, login_required: true }));
  expect(await pending).toEqual({ password_reset: true, login_required: true });
  expect(posts(fetch)).toHaveLength(1);
});

it('bounds confirmation and reconciles without automatically resending after timeout', async () => {
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
  const pending = session.confirmPasswordReset({ ...LINK, ...PASSWORDS });
  await vi.advanceTimersByTimeAsync(AUTH_REQUEST_TIMEOUT_MS);
  expect(await pending).toBeNull();
  expect(posts(fetch)).toHaveLength(1);
  expect(session.busy.value).toBe(false);
});
