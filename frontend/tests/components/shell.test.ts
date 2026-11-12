// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../../src/App.vue';
import { createAppRouter, SITE_TITLE } from '../../src/router.js';

let wrapper: VueWrapper | undefined;
beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn());
  vi.stubGlobal(
    'fetch',
    vi.fn(() => {
      throw new Error('The scaffold must not fetch application data.');
    }),
  );
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.unstubAllGlobals();
});

async function render(path: string) {
  const router = createAppRouter(createMemoryHistory());
  await router.push(path);
  await router.isReady();
  wrapper = mount(App, { attachTo: document.body, global: { plugins: [router] } });
  await flushPromises();
  return { router, app: wrapper };
}

it('renders the home shell with landmarks, a skip link and current navigation', async () => {
  const { app } = await render('/');
  expect(app.get('main h1').text()).toBe('Follow NHL games and players');
  expect(app.get('nav').attributes('aria-label')).toBe('Main navigation');
  expect(app.get('nav a').attributes('aria-current')).toBe('page');
  expect(app.get('.skip-link').attributes('href')).toBe('#main-content');
  expect(document.title).toBe(`Home | ${SITE_TITLE}`);
  expect(fetch).not.toHaveBeenCalled();
});

it('renders an unknown deep link and recovers through client-side home navigation', async () => {
  const { app, router } = await render('/missing/game');
  expect(app.get('h1').text()).toBe('Page not found');
  expect(document.title).toBe(`Page not found | ${SITE_TITLE}`);
  await app.get('.action-link').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.name).toBe('home');
  expect(app.get('h1').text()).toBe('Follow NHL games and players');
  expect(document.activeElement).toBe(app.get('main').element);
  expect(document.title).toBe(`Home | ${SITE_TITLE}`);
  expect(fetch).not.toHaveBeenCalled();
});
