import { inject, readonly, ref, shallowRef, type InjectionKey } from 'vue';
import {
  ApiError,
  authCsrfRetrieve,
  authLoginCreate,
  authLogoutCreate,
  authSessionRetrieve,
  createApiClient,
  type SessionResponse,
  type SessionUser,
} from '../api/index.js';
import type { ApiClientOptions } from '../api/http.js';

export const AUTH_REQUEST_TIMEOUT_MS = 10_000;
type Action = 'login' | 'logout' | 'check';
export type SessionIssue = {
  action: Action;
  message: string;
  reference: string | null;
  fields: { username?: string[]; password?: string[] };
};

function validateIdentity(value: SessionResponse): SessionUser | null {
  if (typeof value.authenticated !== 'boolean') throw new Error('Invalid session response');
  if (!value.authenticated && value.user === null) return null;
  if (
    value.authenticated &&
    value.user &&
    Number.isSafeInteger(value.user.id) &&
    value.user.id > 0 &&
    typeof value.user.username === 'string'
  )
    return { id: value.user.id, username: value.user.username };
  throw new Error('Invalid session response');
}

export function createSession(options: ApiClientOptions = {}) {
  const client = createApiClient(options);
  const user = shallowRef<SessionUser | null>(null);
  const status = ref<'loading' | 'ready' | 'error'>('loading');
  const busy = ref(false);
  const activeAction = ref<Action | null>(null);
  const issue = shallowRef<SessionIssue | null>(null);
  // Future private resources must key/invalidate by identity and this revision.
  const revision = ref(0);
  let disposed = false;
  let pending: AbortController | undefined;

  async function bounded<T>(operation: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const controller = new AbortController();
    pending = controller;
    const timeout = setTimeout(() => controller.abort(), AUTH_REQUEST_TIMEOUT_MS);
    try {
      const result = await operation(controller.signal);
      if (disposed || controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
      return result;
    } finally {
      clearTimeout(timeout);
      if (pending === controller) pending = undefined;
    }
  }
  function unknown() {
    user.value = null;
    status.value = 'loading';
    client.clearCsrfToken();
    revision.value += 1;
  }
  function accept(data: SessionResponse, token: string | null, invalidate = false) {
    const identity = validateIdentity(data);
    if (!token) throw new Error('Missing CSRF token');
    if (invalidate || user.value?.id !== identity?.id || status.value !== 'ready')
      revision.value += 1;
    user.value = identity;
    client.setCsrfToken(token);
    status.value = 'ready';
  }
  async function reconcile(): Promise<boolean> {
    unknown();
    // Isolate token capture: late/aborted responses never restore the app client's token.
    const requestClient = createApiClient(options);
    try {
      const data = await bounded(async (signal) => {
        await authCsrfRetrieve({ client: requestClient, signal });
        if (!requestClient.getCsrfToken() || signal.aborted)
          throw new Error('Missing CSRF bootstrap');
        return (await authSessionRetrieve({ client: requestClient, signal })).data;
      });
      accept(data, requestClient.getCsrfToken());
      return true;
    } catch {
      if (disposed) return false;
      user.value = null;
      client.clearCsrfToken();
      status.value = 'error';
      return false;
    }
  }
  async function checkSession(): Promise<boolean> {
    if (busy.value || disposed) return false;
    busy.value = true;
    activeAction.value = 'check';
    issue.value = null;
    try {
      const success = await reconcile();
      if (!success && !disposed)
        issue.value = {
          action: 'check',
          message: 'Unable to check sign-in status. Please try again.',
          reference: null,
          fields: {},
        };
      return success;
    } finally {
      busy.value = false;
      activeAction.value = null;
    }
  }
  async function mutate(
    action: 'login' | 'logout',
    credentials?: { username: string; password: string },
  ): Promise<boolean> {
    if (busy.value || disposed) return false;
    busy.value = true;
    activeAction.value = action;
    issue.value = null;
    try {
      if (status.value !== 'ready' || !client.getCsrfToken()) {
        if (!(await reconcile())) {
          if (!disposed)
            issue.value = {
              action,
              message:
                'Unable to check sign-in status. Please check your session before trying again.',
              reference: null,
              fields: {},
            };
          return false;
        }
      }
      const requestClient = createApiClient(options);
      requestClient.setCsrfToken(client.getCsrfToken());
      const data = await bounded(async (signal) =>
        action === 'login'
          ? (await authLoginCreate({ client: requestClient, body: credentials!, signal })).data
          : (await authLogoutCreate({ client: requestClient, signal })).data,
      );
      if ((action === 'login') !== data.authenticated)
        throw new Error('Unexpected authentication result');
      if (typeof data.csrf_token !== 'string' || !data.csrf_token)
        throw new Error('Missing rotated CSRF token');
      accept(data, data.csrf_token, true);
      return true;
    } catch (failure) {
      if (disposed) return false;
      const apiError = failure instanceof ApiError ? failure : null;
      const code = apiError?.body.error.code;
      if (action === 'login' && (code === 'invalid_credentials' || code === 'invalid_parameters')) {
        const fields: SessionIssue['fields'] = {};
        if (code === 'invalid_parameters') {
          for (const field of ['username', 'password'] as const) {
            const messages = apiError?.body.error.fields?.[field];
            if (Array.isArray(messages))
              fields[field] = messages.filter(
                (message): message is string => typeof message === 'string',
              );
          }
        }
        issue.value = {
          action,
          message:
            code === 'invalid_credentials'
              ? 'Unable to sign in with those credentials.'
              : 'Check the entered username and password.',
          reference: apiError?.requestId ?? null,
          fields,
        };
      } else {
        // A lost POST response may already have changed the session. Re-read; never replay it.
        await reconcile();
        if (!disposed)
          issue.value = {
            action,
            message:
              code === 'csrf_failed'
                ? 'Your session changed. Review your sign-in status and submit again if needed.'
                : 'The request could not be confirmed. Review your sign-in status before trying again.',
            reference: apiError?.requestId ?? null,
            fields: {},
          };
      }
      return false;
    } finally {
      busy.value = false;
      activeAction.value = null;
    }
  }
  function dispose() {
    disposed = true;
    pending?.abort();
    client.clearCsrfToken();
    user.value = null;
    revision.value += 1;
  }
  return {
    client,
    user: readonly(user),
    status: readonly(status),
    busy: readonly(busy),
    activeAction: readonly(activeAction),
    issue: readonly(issue),
    revision: readonly(revision),
    checkSession,
    login: (credentials: { username: string; password: string }) => mutate('login', credentials),
    logout: () => mutate('logout'),
    dispose,
  };
}
export type Session = ReturnType<typeof createSession>;
export const sessionKey: InjectionKey<Session> = Symbol('session');
export function useSession(): Session {
  const session = inject(sessionKey);
  if (!session) throw new Error('Session provider is required');
  return session;
}
