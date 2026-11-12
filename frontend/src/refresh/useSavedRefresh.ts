import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { Freshness } from '../api/index.js';

export const REFRESH_INTERVAL_MS = 60_000;
export const MAX_REFRESH_DELAY_MS = 300_000;
export const SAVED_READ_TIMEOUT_MS = 10_000;
export const FRESHNESS_TICK_MS = 15_000;
const BACKOFF_FACTOR = 2;
const MILLISECONDS_PER_SECOND = 1_000;

type Options = {
  key: () => string;
  ready: () => boolean;
  freshness: () => Freshness | null;
  refresh: () => Promise<boolean | undefined>;
};

/** Schedules saved-data reads only. Views own request cancellation and publication. */
export function useSavedRefresh(options: Options) {
  const automatic = ref(true);
  const checking = ref(false);
  const failed = ref(false);
  const offline = ref(!navigator.onLine);
  const hidden = ref(document.visibilityState === 'hidden');
  const ready = computed(options.ready);
  const checkedAt = computed(() => options.freshness()?.checked_at ?? null);
  const delay = ref(REFRESH_INTERVAL_MS);
  const clock = ref(performance.now());
  let receivedAt = clock.value;
  let epoch = 0;
  let disposed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let ticker: ReturnType<typeof setInterval> | undefined;

  const stale = computed(() => {
    const metadata = options.freshness();
    if (!metadata?.has_data || metadata.is_final) return false;
    const elapsed = Math.max(0, clock.value - receivedAt) / MILLISECONDS_PER_SECOND;
    return (
      metadata.is_stale ||
      (metadata.age_seconds !== null &&
        metadata.age_seconds + elapsed >= metadata.stale_after_seconds)
    );
  });
  function clearTimer() {
    clearTimeout(timer);
    timer = undefined;
  }
  function schedule() {
    clearTimer();
    if (
      !disposed &&
      automatic.value &&
      ready.value &&
      !checking.value &&
      !hidden.value &&
      !offline.value
    ) {
      timer = setTimeout(() => {
        void run();
      }, delay.value);
    }
  }
  function updateClock() {
    clearInterval(ticker);
    ticker = undefined;
    clock.value = performance.now();
    if (!disposed && ready.value && !hidden.value)
      ticker = setInterval(() => {
        clock.value = performance.now();
      }, FRESHNESS_TICK_MS);
  }
  function reset() {
    epoch += 1;
    checking.value = false;
    failed.value = false;
    delay.value = REFRESH_INTERVAL_MS;
    clearTimer();
  }
  async function run() {
    if (disposed || checking.value || !ready.value || hidden.value || offline.value) return;
    clearTimer();
    const started = ++epoch;
    checking.value = true;
    let result: boolean | undefined;
    try {
      result = await options.refresh();
    } catch {
      result = false;
    }
    if (disposed || started !== epoch) return;
    if (result !== undefined) {
      failed.value = !result;
      delay.value = result
        ? REFRESH_INTERVAL_MS
        : Math.min(delay.value * BACKOFF_FACTOR, MAX_REFRESH_DELAY_MS);
    }
    checking.value = false;
    schedule();
  }
  function setAutomatic(value: boolean) {
    automatic.value = value;
    schedule();
  }
  function connectivityChanged() {
    offline.value = !navigator.onLine;
    schedule();
    if (!offline.value && automatic.value) void run();
  }
  function visibilityChanged() {
    hidden.value = document.visibilityState === 'hidden';
    updateClock();
    schedule();
    if (!hidden.value && automatic.value) void run();
  }

  watch(options.key, reset);
  watch(ready, () => {
    updateClock();
    schedule();
  });
  watch(
    options.freshness,
    (metadata) => {
      if (!metadata) return;
      receivedAt = performance.now();
      clock.value = receivedAt;
      failed.value = false;
      delay.value = REFRESH_INTERVAL_MS;
      schedule();
    },
    { immediate: true, flush: 'sync' },
  );
  onMounted(() => {
    document.addEventListener('visibilitychange', visibilityChanged);
    window.addEventListener('online', connectivityChanged);
    window.addEventListener('offline', connectivityChanged);
    updateClock();
    schedule();
  });
  onBeforeUnmount(() => {
    disposed = true;
    reset();
    clearInterval(ticker);
    document.removeEventListener('visibilitychange', visibilityChanged);
    window.removeEventListener('online', connectivityChanged);
    window.removeEventListener('offline', connectivityChanged);
  });
  return {
    automatic,
    checking,
    failed,
    offline,
    hidden,
    ready,
    checkedAt,
    stale,
    delay,
    run,
    reset,
    setAutomatic,
  };
}
export type SavedRefresh = ReturnType<typeof useSavedRefresh>;
