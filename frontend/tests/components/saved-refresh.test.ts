// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, ref, shallowRef } from 'vue';
import { mount, type VueWrapper } from '@vue/test-utils';
import {
  useSavedRefresh,
  type SavedRefresh,
  REFRESH_INTERVAL_MS,
  MAX_REFRESH_DELAY_MS,
  FRESHNESS_TICK_MS,
} from '../../src/refresh/useSavedRefresh.js';
import { freshness } from '../fixtures/scoreboard.js';

let wrapper: VueWrapper | undefined;
let hidden = false;
let online = true;
beforeEach(() => {
  vi.useFakeTimers();
  hidden = false;
  online = true;
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() =>
    hidden ? 'hidden' : 'visible',
  );
  vi.spyOn(navigator, 'onLine', 'get').mockImplementation(() => online);
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.useRealTimers();
  vi.restoreAllMocks();
});
function harness(refresh = vi.fn<() => Promise<boolean | undefined>>().mockResolvedValue(true)) {
  const key = ref('game-one');
  const ready = ref(true);
  const metadata = shallowRef(freshness());
  let state!: SavedRefresh;
  wrapper = mount(
    defineComponent({
      setup() {
        state = useSavedRefresh({
          key: () => key.value,
          ready: () => ready.value,
          freshness: () => metadata.value,
          refresh,
        });
        return () => h('div');
      },
    }),
  );
  return { state, key, ready, metadata, refresh };
}

it('checks visible saved data every minute and permits manual refresh while automatic checks are paused', async () => {
  const { state, refresh } = harness();
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS - 1);
  expect(refresh).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  expect(refresh).toHaveBeenCalledTimes(1);
  state.setAutomatic(false);
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2);
  expect(refresh).toHaveBeenCalledTimes(1);
  await state.run();
  expect(refresh).toHaveBeenCalledTimes(2);
});

it('prevents overlap and schedules from completion rather than piling up interval requests', async () => {
  let finish!: (success: boolean) => void;
  const refresh = vi.fn<() => Promise<boolean | undefined>>(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { state } = harness(refresh);
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  expect(state.checking.value).toBe(true);
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 4);
  await state.run();
  expect(refresh).toHaveBeenCalledTimes(1);
  finish(true);
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS - 1);
  expect(refresh).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(refresh).toHaveBeenCalledTimes(2);
});

it('pauses hidden/offline tabs and checks once on return without overriding the pause toggle', async () => {
  const { state, refresh } = harness();
  hidden = true;
  document.dispatchEvent(new Event('visibilitychange'));
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2);
  expect(refresh).not.toHaveBeenCalled();
  hidden = false;
  document.dispatchEvent(new Event('visibilitychange'));
  await vi.advanceTimersByTimeAsync(0);
  expect(refresh).toHaveBeenCalledTimes(1);
  online = false;
  window.dispatchEvent(new Event('offline'));
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2);
  await state.run();
  expect(refresh).toHaveBeenCalledTimes(1);
  online = true;
  window.dispatchEvent(new Event('online'));
  await vi.advanceTimersByTimeAsync(0);
  expect(refresh).toHaveBeenCalledTimes(2);
  state.setAutomatic(false);
  hidden = true;
  document.dispatchEvent(new Event('visibilitychange'));
  hidden = false;
  document.dispatchEvent(new Event('visibilitychange'));
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2);
  expect(refresh).toHaveBeenCalledTimes(2);
});

it('backs off failed checks to five minutes, preserves check/save timestamps and resets after success', async () => {
  const refresh = vi.fn<() => Promise<boolean | undefined>>().mockResolvedValue(false);
  const { state, metadata } = harness(refresh);
  const original = { ...metadata.value };
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
  expect(state.failed.value).toBe(true);
  expect(state.delay.value).toBe(120_000);
  await vi.advanceTimersByTimeAsync(120_000);
  expect(state.delay.value).toBe(240_000);
  await vi.advanceTimersByTimeAsync(240_000);
  expect(state.delay.value).toBe(MAX_REFRESH_DELAY_MS);
  await vi.advanceTimersByTimeAsync(MAX_REFRESH_DELAY_MS);
  expect(state.delay.value).toBe(MAX_REFRESH_DELAY_MS);
  expect(metadata.value).toEqual(original);
  expect(state.checkedAt.value).toBe(original.checked_at);
  refresh.mockResolvedValue(true);
  await state.run();
  expect(state.failed.value).toBe(false);
  expect(state.delay.value).toBe(REFRESH_INTERVAL_MS);
});

it('discards an old selection check without corrupting the new selection or its active check', async () => {
  const finishes: Array<(value: boolean) => void> = [];
  const refresh = vi.fn<() => Promise<boolean | undefined>>(
    () =>
      new Promise((resolve) => {
        finishes.push(resolve);
      }),
  );
  const { state, key } = harness(refresh);
  const old = state.run();
  key.value = 'game-two';
  await nextTick();
  const current = state.run();
  finishes[0]!(false);
  await old;
  expect(state.checking.value).toBe(true);
  expect(state.failed.value).toBe(false);
  finishes[1]!(true);
  await current;
  expect(state.checking.value).toBe(false);
});

it('ages unfinished saved data using server age and monotonic elapsed time even while auto-refresh is paused', async () => {
  const { state, metadata } = harness();
  state.setAutomatic(false);
  metadata.value = freshness({
    age_seconds: 890,
    stale_after_seconds: 900,
    saved_at: '2000-01-01T00:00:00Z',
  });
  expect(state.stale.value).toBe(false);
  await vi.advanceTimersByTimeAsync(FRESHNESS_TICK_MS);
  expect(state.stale.value).toBe(true);
  metadata.value = freshness({ age_seconds: 999_999, is_final: true });
  await vi.advanceTimersByTimeAsync(FRESHNESS_TICK_MS);
  expect(state.stale.value).toBe(false);
  metadata.value = freshness({ has_data: false, age_seconds: null, saved_at: null });
  expect(state.stale.value).toBe(false);
});

it('does not poll before readiness or after unmount and removes visibility/online handlers', async () => {
  const { state, ready, refresh } = harness();
  ready.value = false;
  await nextTick();
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2);
  expect(refresh).not.toHaveBeenCalled();
  ready.value = true;
  await nextTick();
  wrapper!.unmount();
  wrapper = undefined;
  document.dispatchEvent(new Event('visibilitychange'));
  window.dispatchEvent(new Event('online'));
  await state.run();
  await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2);
  expect(refresh).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});
