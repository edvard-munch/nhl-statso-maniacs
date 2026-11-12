import { onBeforeUnmount, readonly, ref, shallowRef, watch } from 'vue';
import { ApiError, ApiProtocolError } from '../api/index.js';
import type { ApiClient } from '../api/http.js';
import type { Session } from '../auth/session.js';
import { SAVED_READ_TIMEOUT_MS } from '../refresh/useSavedRefresh.js';

type PrivatePhase =
  | 'waiting'
  | 'anonymous'
  | 'session-error'
  | 'invalid'
  | 'loading'
  | 'ready'
  | 'error'
  | 'forbidden';
/** Component-local private data: no persistence, public cache or last-good retention. */
export function usePrivateRead<T>(
  session: Session,
  options: {
    key: () => string;
    valid: () => boolean;
    read: (client: ApiClient, signal: AbortSignal) => Promise<T>;
  },
) {
  const phase = ref<PrivatePhase>('waiting');
  const data = shallowRef<T | null>(null);
  const reference = ref<string | null>(null);
  const httpStatus = ref<number | null>(null);
  let controller: AbortController | undefined;
  let disposed = false;
  function clear() {
    controller?.abort();
    controller = undefined;
    data.value = null;
    reference.value = null;
    httpStatus.value = null;
  }
  function eligible() {
    return (
      !disposed && session.status.value === 'ready' && !!session.user.value && !session.busy.value
    );
  }
  async function load() {
    clear();
    if (disposed) return;
    if (session.status.value === 'error') {
      phase.value = 'session-error';
      return;
    }
    if (session.status.value !== 'ready' || session.busy.value) {
      phase.value = 'waiting';
      return;
    }
    if (!session.user.value) {
      phase.value = 'anonymous';
      return;
    }
    if (!options.valid()) {
      phase.value = 'invalid';
      return;
    }
    const owner = session.user.value.id;
    const revision = session.revision.value;
    const key = options.key();
    const current = new AbortController();
    controller = current;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      current.abort();
    }, SAVED_READ_TIMEOUT_MS);
    const stale = () =>
      controller !== current ||
      !eligible() ||
      session.user.value?.id !== owner ||
      session.revision.value !== revision ||
      options.key() !== key;
    phase.value = 'loading';
    try {
      const response = await options.read(session.client, current.signal);
      if (stale() || current.signal.aborted) return;
      data.value = response;
      phase.value = 'ready';
    } catch (failure) {
      if (stale() || (current.signal.aborted && !timedOut)) return;
      data.value = null;
      if (failure instanceof ApiError || failure instanceof ApiProtocolError) {
        reference.value = failure.requestId;
        httpStatus.value = failure.response.status;
      }
      // No automatic session-check/read loop. A 403 requires an explicit check.
      phase.value = httpStatus.value === 403 ? 'forbidden' : 'error';
    } finally {
      clearTimeout(timeout);
    }
  }
  const stop = watch(
    [
      options.key,
      options.valid,
      () => session.status.value,
      () => session.user.value?.id,
      () => session.revision.value,
      () => session.busy.value,
    ],
    () => {
      void load();
    },
    { immediate: true, flush: 'sync' },
  );
  onBeforeUnmount(() => {
    disposed = true;
    stop();
    clear();
    phase.value = 'waiting';
  });
  return {
    phase: readonly(phase),
    data: readonly(data),
    reference: readonly(reference),
    httpStatus: readonly(httpStatus),
    reload: load,
  };
}
