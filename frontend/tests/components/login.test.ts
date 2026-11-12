// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { createSession, sessionKey } from '../../src/auth/session.js';
import { safeReturnLocation } from '../../src/auth/returnLocation.js';

let wrapper: VueWrapper | undefined;
beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()));
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.unstubAllGlobals();
});
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
async function render(path = '/login', invalid = false) {
  const posts: RequestInit[] = [];
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/csrf/')) return json({ csrf_token: 'initial' });
    if (url.endsWith('/session/')) return json({ authenticated: false, user: null });
    posts.push(init!);
    return invalid
      ? json({ error: { code: 'invalid_credentials', message: 'Generic failure.' } }, 400)
      : json({ authenticated: true, user: { id: 1, username: 'first' }, csrf_token: 'rotated' });
  });
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
  return { app: wrapper, router, session, posts, fetch };
}

it('renders labelled credential inputs and preserves exact password while clearing it after an error', async () => {
  const { app, posts } = await render('/login', true);
  await app.get('#login-username').setValue('first');
  await app.get('#login-password').setValue('  secret  ');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(String(posts[0]!.body))).toEqual({ username: 'first', password: '  secret  ' });
  expect(app.get('[role="alert"]').text()).toContain('Unable to sign in with those credentials');
  expect((app.get('#login-password').element as HTMLInputElement).value).toBe('');
  expect((app.get('#login-username').element as HTMLInputElement).value).toBe('first');
  expect(app.get('#login-password').attributes('autocomplete')).toBe('current-password');
});

it('updates the shared header and safely navigates after a successful sign-in', async () => {
  const { app, router } = await render('/login?returnTo=%2F');
  await app.get('#login-username').setValue('first');
  await app.get('#login-password').setValue('secret');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe('/');
  expect(app.get('[aria-label="Sign-in status"]').text()).toContain('Signed in as first');
});

it.each([
  'https://example.com',
  '//example.com',
  '/\\example.com',
  '/login',
  '/missing',
  '/games\n/1',
])('rejects unsafe or unsupported return target %s', async (value) => {
  const router = createAppRouter(createMemoryHistory());
  expect(safeReturnLocation(value, router)).toBe('/');
});

it('keeps valid local scoreboard query context in the return target', () => {
  const router = createAppRouter(createMemoryHistory());
  expect(safeReturnLocation('/games?date=2026-11-12&page=2', router)).toBe(
    '/games?date=2026-11-12&page=2',
  );
});

it('does not redirect from an unmounted login form when its pending sign-in completes', async () => {
  const { app, router, session, fetch } = await render('/login');
  let finish!: (response: Response) => void;
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await app.get('#login-username').setValue('first');
  await app.get('#login-password').setValue('secret');
  await app.get('form').trigger('submit');
  await router.push('/missing');
  await flushPromises();
  finish(json({ authenticated: true, user: { id: 1, username: 'first' }, csrf_token: 'rotated' }));
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe('/missing');
  expect(session.user.value?.id).toBe(1);
  expect(app.get('h1').text()).toBe('Page not found');
});
