import { inject, readonly, ref, shallowRef, type InjectionKey } from 'vue';
import {
  ApiError,
  authCsrfRetrieve,
  authLoginCreate,
  authLogoutCreate,
  authRegisterCreate,
  authPasswordResetCreate,
  authPasswordResetValidateCreate,
  authPasswordResetConfirmCreate,
  authSessionRetrieve,
  createApiClient,
  type SessionResponse,
  type RegistrationCredentialsRequest,
  type RegistrationResponse,
  type PasswordRecoveryRequestRequest,
  type ResetLinkRequest,
  type NewPasswordRequest,
  type SessionUser,
} from '../api/index.js';
import type { ApiClient, ApiClientOptions } from '../api/http.js';

export const AUTH_REQUEST_TIMEOUT_MS = 10_000;
const HTTP_CREATED = 201;
type RecoveryAction = 'reset-request' | 'reset-validate' | 'reset-confirm';
type Action = 'login' | 'logout' | 'register' | 'check' | RecoveryAction;
export type SessionIssue = {
  action: Action;
  code?: string;
  message: string;
  reference: string | null;
  fields: Partial<
    Record<
      | 'username'
      | 'password'
      | 'email'
      | 'password1'
      | 'password2'
      | 'non_field_errors'
      | 'new_password1'
      | 'new_password2',
      string[]
    >
  >;
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
  async function register(
    credentials: RegistrationCredentialsRequest,
  ): Promise<RegistrationResponse | null> {
    if (busy.value || disposed) return null;
    busy.value = true;
    activeAction.value = 'register';
    issue.value = null;
    try {
      if (status.value !== 'ready' || !client.getCsrfToken()) {
        if (!(await reconcile())) {
          if (!disposed)
            issue.value = {
              action: 'register',
              message:
                'Unable to check sign-in status. Check your session before creating an account.',
              reference: null,
              fields: {},
            };
          return null;
        }
      }
      const requestClient = createApiClient(options);
      requestClient.setCsrfToken(client.getCsrfToken());
      const response = await bounded((signal) =>
        authRegisterCreate({ client: requestClient, body: credentials, signal }),
      );
      if (response.response.status !== HTTP_CREATED)
        throw new Error('Unexpected registration status');
      const data = response.data;
      const created = validateIdentity({ authenticated: true, user: data.user });
      if (data.login_required !== true || !created)
        throw new Error('Unexpected registration result');
      // This identity is the NEW account, never the caller's session identity.
      // Registration does not rotate CSRF or sign in; do not call accept().
      return { user: created, login_required: true };
    } catch (failure) {
      if (disposed) return null;
      const apiError = failure instanceof ApiError ? failure : null;
      if (apiError?.body.error.code === 'invalid_parameters') {
        const fields: SessionIssue['fields'] = {};
        for (const field of [
          'username',
          'email',
          'password1',
          'password2',
          'non_field_errors',
        ] as const) {
          const messages = apiError.body.error.fields?.[field];
          if (Array.isArray(messages))
            fields[field] = messages.filter(
              (message): message is string => typeof message === 'string',
            );
        }
        issue.value = {
          action: 'register',
          message: 'Check the registration fields below.',
          reference: apiError.requestId,
          fields,
        };
      } else {
        // A lost response can hide successful creation. Reconcile ONLY the caller's
        // session and token; never resubmit registration or infer account creation.
        await reconcile();
        if (!disposed)
          issue.value = {
            action: 'register',
            message:
              apiError?.body.error.code === 'csrf_failed'
                ? 'Your session changed. Review your sign-in status and submit again if needed.'
                : 'Account creation could not be confirmed. Check whether you can sign in before trying to create this account again.',
            reference: apiError?.requestId ?? null,
            fields: {},
          };
      }
      return null;
    } finally {
      busy.value = false;
      activeAction.value = null;
    }
  }
  async function recover<T>(
    action: RecoveryAction,
    request: (requestClient: ApiClient, signal: AbortSignal) => Promise<T>,
    valid: (data: T) => boolean,
  ): Promise<T | null> {
    if (busy.value || disposed) return null;
    busy.value = true;
    activeAction.value = action;
    issue.value = null;
    try {
      if (status.value !== 'ready' || !client.getCsrfToken()) {
        if (!(await reconcile())) {
          if (!disposed)
            issue.value = {
              action,
              code: 'session_unavailable',
              message: 'Check your session before continuing password recovery.',
              reference: null,
              fields: {},
            };
          return null;
        }
      }
      const requestClient = createApiClient(options);
      requestClient.setCsrfToken(client.getCsrfToken());
      const data = await bounded((signal) => request(requestClient, signal));
      if (!valid(data)) throw new Error('Unexpected password recovery result');
      // Reset can invalidate this browser's target session. Confirmation is still
      // known successful even if the following session read is unavailable.
      if (action === 'reset-confirm') await reconcile();
      return disposed ? null : data;
    } catch (failure) {
      if (disposed) return null;
      const apiError = failure instanceof ApiError ? failure : null;
      const code = apiError?.body.error.code;
      const fields: SessionIssue['fields'] = {};
      if (code === 'invalid_parameters') {
        const allowed =
          action === 'reset-request'
            ? (['email', 'non_field_errors'] as const)
            : (['new_password1', 'new_password2', 'non_field_errors'] as const);
        for (const field of allowed) {
          const messages = apiError?.body.error.fields?.[field];
          if (Array.isArray(messages))
            fields[field] = messages.filter(
              (message): message is string => typeof message === 'string',
            );
        }
      } else if (code !== 'invalid_reset_token' && code !== 'password_reset_unavailable') {
        // Reconcile the caller only. Never retry mail or password-changing POSTs.
        await reconcile();
      }
      if (disposed) return null;
      const message =
        code === 'invalid_reset_token'
          ? 'This reset link is invalid or no longer available.'
          : code === 'password_reset_unavailable'
            ? 'Password recovery is currently unavailable. Please try later.'
            : code === 'invalid_parameters'
              ? 'Check the recovery fields below.'
              : code === 'csrf_failed'
                ? 'Your session changed. Review your sign-in status and submit again if needed.'
                : action === 'reset-request'
                  ? 'The request could not be confirmed. Check your email before choosing to send another request.'
                  : action === 'reset-validate'
                    ? 'Unable to check this reset link. Please try again.'
                    : 'Password change could not be confirmed. Try signing in before checking this link or requesting another.';
      issue.value = {
        action,
        code: code ?? 'unconfirmed',
        message,
        reference: apiError?.requestId ?? null,
        fields,
      };
      return null;
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
    register,
    requestPasswordReset: (body: PasswordRecoveryRequestRequest) =>
      recover(
        'reset-request',
        (requestClient, signal) =>
          authPasswordResetCreate({ client: requestClient, body, signal }).then(
            (result) => result.data,
          ),
        (data) => data.accepted === true,
      ),
    validatePasswordReset: (body: ResetLinkRequest) =>
      recover(
        'reset-validate',
        (requestClient, signal) =>
          authPasswordResetValidateCreate({ client: requestClient, body, signal }).then(
            (result) => result.data,
          ),
        (data) => data.valid === true,
      ),
    confirmPasswordReset: (body: NewPasswordRequest) =>
      recover(
        'reset-confirm',
        (requestClient, signal) =>
          authPasswordResetConfirmCreate({ client: requestClient, body, signal }).then(
            (result) => result.data,
          ),
        (data) => data.password_reset === true && data.login_required === true,
      ),
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
