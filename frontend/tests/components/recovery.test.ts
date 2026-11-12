// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter } from '../../src/router.js';
import { createSession, sessionKey } from '../../src/auth/session.js';
import { createResetLinkSlot, resetLinkKey } from '../../src/auth/resetLink.js';

let wrapper: VueWrapper | undefined;
beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()));
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.unstubAllGlobals();
});
const LINK = { uidb64: 'MQ', token: 'test-reset-secret' };
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
async function render(confirm = false, missing = false) {
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith('/csrf/')) return json({ csrf_token: 'current' });
    if (url.endsWith('/session/')) return json({ authenticated: false, user: null });
    if (url.endsWith('/validate/')) return json({ valid: true });
    if (url.endsWith('/confirm/')) return json({ password_reset: true, login_required: true });
    return json({ accepted: true });
  });
  const session = createSession({ fetch });
  const slot = createResetLinkSlot(missing ? null : LINK);
  const router = createAppRouter(createMemoryHistory());
  await router.push(confirm ? '/recover-password/' : '/password-reset');
  await router.isReady();
  wrapper = mount(App, {
    global: {
      plugins: [router],
      provide: { [sessionKey as symbol]: session, [resetLinkKey as symbol]: slot },
    },
  });
  await session.checkSession();
  await flushPromises();
  return { app: wrapper, router, session, slot, fetch };
}

it('uses a generic acknowledgement and clears submitted email without confirming delivery', async () => {
  const { app, fetch } = await render();
  await app.get('#reset-email').setValue('unknown@example.invalid');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('h2').text()).toBe('Request received');
  expect(app.text()).toContain('does not confirm an account exists or that email was delivered');
  expect(app.text()).not.toContain('unknown@example.invalid');
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
});

it('shows mail field/configuration errors without inventing a matching account', async () => {
  const { app, fetch } = await render();
  fetch.mockImplementationOnce(async () =>
    json({ error: { code: 'password_reset_unavailable', message: 'Unavailable.' } }, 503),
  );
  await app.get('#reset-email').setValue('any@example.invalid');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('currently unavailable');
  expect(app.find('h2').exists()).toBe(false);
});

it('validates once, keeps the link out of DOM and clears passwords after correctable errors', async () => {
  const { app, fetch } = await render(true);
  expect(fetch.mock.calls.filter(([input]) => String(input).endsWith('/validate/'))).toHaveLength(
    1,
  );
  expect(app.html()).not.toContain(LINK.uidb64);
  expect(app.html()).not.toContain(LINK.token);
  fetch.mockImplementationOnce(async () =>
    json(
      {
        error: {
          code: 'invalid_parameters',
          message: 'Invalid.',
          fields: { new_password2: ['Passwords do not match.'] },
        },
      },
      400,
    ),
  );
  await app.get('#reset-password1').setValue('  new password  ');
  await app.get('#reset-password2').setValue('different');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('#new-password2-errors').text()).toContain('Passwords do not match');
  expect((app.get('#reset-password1').element as HTMLInputElement).value).toBe('');
  expect((app.get('#reset-password2').element as HTMLInputElement).value).toBe('');
  await app.get('#reset-password1').setValue('  new password  ');
  await app.get('#reset-password2').setValue('  new password  ');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('h2').text()).toBe('Password changed');
  expect(app.find('form').exists()).toBe(false);
  expect(fetch.mock.calls.some(([input]) => String(input).endsWith('/login/'))).toBe(false);
});

it('shows missing/used links generically and never submits without memory credentials', async () => {
  const { app, fetch } = await render(true, true);
  expect(app.get('[role="alert"]').text()).toContain('invalid or no longer available');
  expect(fetch.mock.calls.some(([input]) => String(input).includes('/password-reset/'))).toBe(
    false,
  );
});

it('does not consume another link when navigating back after leaving the confirmation view', async () => {
  const { app, router, slot } = await render(true);
  expect(slot.take()).toBeNull();
  await router.push('/');
  await router.push('/recover-password/');
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('invalid or no longer available');
});

it('keeps uncertain confirmation separate from success and requires explicit link revalidation', async () => {
  const { app, fetch } = await render(true);
  fetch.mockImplementationOnce(async () => {
    throw new TypeError('Lost confirmation');
  });
  await app.get('#reset-password1').setValue('new password');
  await app.get('#reset-password2').setValue('new password');
  await app.get('form').trigger('submit');
  await flushPromises();
  expect(app.get('[role="alert"]').text()).toContain('Password change could not be confirmed');
  expect(app.find('form').exists()).toBe(false);
  expect(fetch.mock.calls.filter(([input]) => String(input).endsWith('/confirm/'))).toHaveLength(1);
  await app.get('button').trigger('click');
  await flushPromises();
  expect(app.find('form').exists()).toBe(true);
  expect(fetch.mock.calls.filter(([input]) => String(input).endsWith('/confirm/'))).toHaveLength(1);
});
