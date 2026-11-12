// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { createSession, sessionKey } from '../../src/auth/session.js';
import { registration } from '../fixtures/registration.js';

let wrapper: VueWrapper | undefined;
beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()));
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.unstubAllGlobals();
});
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
async function render(signedIn = false, path = '/register') {
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith('/csrf/')) return json({ csrf_token: 'initial' });
    if (url.endsWith('/session/'))
      return json({
        authenticated: signedIn,
        user: signedIn ? { id: 7, username: 'existing' } : null,
      });
    return json({ user: { id: 42, username: 'new-user' }, login_required: true }, 201);
  });
  const session = createSession({ fetch });
  const router = createAppRouter(createMemoryHistory());
  await router.push(path);
  await router.isReady();
  wrapper = mount(App, {
    global: { plugins: [router], provide: { [sessionKey as symbol]: session } },
  });
  await session.checkSession();
  await flushPromises();
  return { app: wrapper, router, session, fetch };
}
async function fill(app: VueWrapper) {
  for (const [field, value] of Object.entries(registration()))
    await app.get(`#register-${field}`).setValue(value);
}

it('shows accessible fields and creates an account without automatic login or navigation', async () => {
  const { app, session, router, fetch } = await render(
    false,
    '/register?returnTo=%2Fgames%3Fdate%3D2026-11-12%26page%3D2',
  );
  expect(app.get('#register-email').attributes('type')).toBe('email');
  expect(app.get('#register-password1').attributes('autocomplete')).toBe('new-password');
  expect(app.get('#register-password2').attributes('autocomplete')).toBe('new-password');
  await fill(app);
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('h2').text()).toBe('Account created');
  expect(app.text()).toContain('You have not been signed in');
  expect(app.find('form').exists()).toBe(false);
  expect(session.user.value).toBeNull();
  expect(router.currentRoute.value.name).toBe('register');
  const signIn = new URL(
    app.get('[aria-labelledby="created-title"] a').attributes('href')!,
    'https://nhl.test',
  );
  expect(signIn.pathname).toBe('/login');
  expect(signIn.searchParams.get('returnTo')).toBe('/games?date=2026-11-12&page=2');
  const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')!;
  expect(JSON.parse(String(post[1]?.body))).toEqual(registration());
  expect(fetch.mock.calls.some(([input]) => String(input).endsWith('/login/'))).toBe(false);
});

it('shows field errors, retains username/email and clears both passwords after validation failure', async () => {
  const { app, fetch } = await render();
  fetch.mockImplementationOnce(async () =>
    json(
      {
        error: {
          code: 'invalid_parameters',
          message: 'Invalid.',
          fields: {
            username: ['Already exists.'],
            email: ['Enter a valid email.'],
            password2: ['Passwords do not match.'],
            non_field_errors: ['Check these details.'],
          },
        },
      },
      400,
    ),
  );
  await fill(app);
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Check these details.');
  expect(app.get('#register-username').attributes('aria-invalid')).toBe('true');
  expect(app.get('#register-password2').attributes('aria-describedby')).toBe(
    'register-password2-errors',
  );
  expect(app.get('#register-password2-errors').text()).toContain('Passwords do not match.');
  expect((app.get('#register-username').element as HTMLInputElement).value).toBe('new-user');
  expect((app.get('#register-email').element as HTMLInputElement).value).toBe(
    'reused@example.invalid',
  );
  expect((app.get('#register-password1').element as HTMLInputElement).value).toBe('');
  expect((app.get('#register-password2').element as HTMLInputElement).value).toBe('');
});

it('keeps a signed-in caller separate from the created identity', async () => {
  const { app, session } = await render(true);
  await fill(app);
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(session.user.value?.id).toBe(7);
  expect(app.get('[aria-label="Sign-in status"]').text()).toContain('Signed in as existing');
  expect(app.get('[aria-labelledby="created-title"]').text()).toContain('new-user');
  expect(app.get('[aria-labelledby="created-title"]').text()).toContain(
    'still signed in as existing',
  );
});

it('shows uncertainty after a proxy failure, not false success or a blind retry', async () => {
  const { app, fetch } = await render();
  fetch.mockImplementationOnce(
    async () =>
      new Response('private proxy detail', {
        status: 502,
        headers: { 'Content-Type': 'text/html' },
      }),
  );
  await fill(app);
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Account creation could not be confirmed');
  expect(app.text()).not.toContain('private proxy detail');
  expect(app.find('h2').exists()).toBe(false);
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
});

it('ignores late completion after navigating away and keeps the caller anonymous', async () => {
  const { app, router, session, fetch } = await render();
  let finish!: (response: Response) => void;
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await fill(app);
  await app.get('form').trigger('submit');
  await router.push('/');
  await flushPromises();
  finish(json({ user: { id: 42, username: 'new-user' }, login_required: true }, 201));
  await flushPromises();
  expect(router.currentRoute.value.name).toBe('home');
  expect(app.text()).not.toContain('Account created');
  expect(session.user.value).toBeNull();
});

it('does not submit incomplete fields', async () => {
  const { app, fetch } = await render();
  await app.get('form').trigger('submit');
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
});
