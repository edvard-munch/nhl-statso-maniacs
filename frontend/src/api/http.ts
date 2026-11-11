/** Same-origin Django transport owned by the app; generated SDK files stay untouched. */
import type { ErrorResponse } from './generated/types.js';
export const API_PREFIX = '/api/v1/';
export const CSRF_HEADER = 'X-CSRFToken';
const JSON_TYPE = 'application/json';
const MULTIPART_TYPE = 'multipart/form-data';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
const EMPTY_STATUSES = new Set([204, 205]);
const TOKEN_ENDPOINTS = new Set([
  '/api/v1/auth/csrf/', '/api/v1/auth/login/', '/api/v1/auth/logout/',
]);

type DataShape = { body?: unknown; headers?: unknown; path?: unknown; query?: unknown };
type HeaderFields<T extends DataShape> = NonNullable<T['headers']>;
type ManagedHeaders<H> = Omit<H, typeof CSRF_HEADER> & Partial<Pick<H, Extract<keyof H, typeof CSRF_HEADER>>>;
type HeaderOptions<T extends DataShape> = 'headers' extends keyof T
  ? {} extends Omit<HeaderFields<T>, typeof CSRF_HEADER>
    ? { headers?: ManagedHeaders<HeaderFields<T>> }
    : { headers: ManagedHeaders<HeaderFields<T>> }
  : { headers?: object };

export type RequestConfig = {
  method: 'GET' | 'HEAD' | 'OPTIONS' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  url: string;
  headers?: object;
  path?: object;
  query?: object;
  body?: unknown;
  signal?: AbortSignal;
  throwOnError?: boolean;
  contentType?: { request?: string; response?: string };
  security?: ReadonlyArray<{ type: string; name?: string; in?: string; scopes?: string[] }>;
  client?: Transport;
};

export type Options<T extends DataShape, Throw extends boolean = true> =
  Omit<RequestConfig, keyof DataShape | 'method' | 'url' | 'throwOnError'> &
  Omit<T, 'headers'> & HeaderOptions<T> & { throwOnError?: Throw };

type SuccessBody<T> = {
  [Code in keyof T]: `${Code & (string | number)}` extends `2${string}`
    ? `${Code & (string | number)}` extends '204' | '205' ? undefined : T[Code]
    : never
}[keyof T];
type ErrorBody<T> = {
  [Code in keyof T]: `${Code & (string | number)}` extends `2${string}` ? never : T[Code]
}[keyof T];
export type RequestResult<T, Throw extends boolean = true> =
  | { data: SuccessBody<T>; error: undefined; response: Response }
  | (Throw extends true ? never : { data: undefined; error: ErrorBody<T>; response: Response });

type TransportResult = { data: unknown; error: undefined; response: Response }
  | { data: undefined; error: unknown; response: Response };
export type Transport = (config: RequestConfig) => Promise<TransportResult>;
export interface ApiClient extends Transport {
  setCsrfToken(token: string | null): void;
  clearCsrfToken(): void;
  getCsrfToken(): string | null;
}
export type ApiClientOptions = { origin?: string; fetch?: typeof globalThis.fetch };
export type ErrorEnvelope = ErrorResponse;

export class ApiError extends Error {
  readonly requestId: string | null;
  constructor(readonly body: ErrorEnvelope, readonly response: Response) {
    super(body.error.message);
    this.name = 'ApiError';
    this.requestId = response.headers.get('X-Request-ID');
  }
}
export class ApiProtocolError extends Error {
  readonly requestId: string | null;
  constructor(message: string, readonly response: Response) {
    super(message);
    this.name = 'ApiProtocolError';
    this.requestId = response.headers.get('X-Request-ID');
  }
}
export class CsrfTokenRequiredError extends Error {
  constructor() {
    super('Bootstrap CSRF before sending an unsafe API request.');
    this.name = 'CsrfTokenRequiredError';
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function errorEnvelope(value: unknown): value is ErrorEnvelope {
  return record(value) && record(value.error)
    && typeof value.error.code === 'string' && typeof value.error.message === 'string'
    && (value.error.fields === undefined || record(value.error.fields));
}

function requestUrl(config: RequestConfig, origin: string): URL {
  const base = new URL(origin);
  const parameters: Record<string, unknown> = { ...config.path };
  const resolved = config.url.replace(/\{([^}]+)\}/g, (_, key: string) => {
    if (parameters[key] === undefined || parameters[key] === null) throw new TypeError(`Missing path parameter: ${key}`);
    return encodeURIComponent(String(parameters[key]));
  });
  const url = new URL(resolved, base.origin);
  if (!['http:', 'https:'].includes(base.protocol) || url.origin !== base.origin
      || !url.pathname.startsWith(API_PREFIX) || url.username || url.password || url.hash) {
    throw new TypeError('Only same-origin /api/v1/ requests are allowed.');
  }
  for (const [key, value] of Object.entries(config.query ?? {})) {
    if (value !== undefined && value !== null) {
      for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(item));
    }
  }
  return url;
}

function requestBody(config: RequestConfig, headers: Headers): BodyInit | undefined {
  if (config.body === undefined) return undefined;
  const multipart = config.body instanceof FormData || config.contentType?.request === MULTIPART_TYPE;
  if (multipart) {
    headers.delete('Content-Type'); // fetch owns the multipart boundary.
    if (config.body instanceof FormData) return config.body;
    if (!record(config.body)) throw new TypeError('Multipart bodies must be field objects or FormData.');
    const form = new FormData();
    for (const [key, value] of Object.entries(config.body)) {
      if (value !== undefined && value !== null) {
        if (value instanceof Blob) form.append(key, value);
        else form.append(key, String(value));
      }
    }
    return form;
  }
  headers.set('Content-Type', JSON_TYPE);
  return JSON.stringify(config.body);
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  let csrfToken: string | null = null;
  const request: Transport = async config => {
    const browserOrigin = globalThis.location?.origin;
    const origin = options.origin ?? browserOrigin;
    if (!origin) throw new TypeError('An API origin is required outside the browser.');
    if (browserOrigin && new URL(origin).origin !== browserOrigin) {
      throw new TypeError('The API origin must match the browser origin.');
    }
    const url = requestUrl(config, origin);
    const headers = new Headers(config.headers as HeadersInit | undefined);
    headers.set('Accept', JSON_TYPE);
    if (!SAFE_METHODS.has(config.method)) {
      const token = csrfToken ?? headers.get(CSRF_HEADER);
      if (!token) throw new CsrfTokenRequiredError();
      headers.set(CSRF_HEADER, token);
    }
    const body = requestBody(config, headers);
    const response = await (options.fetch ?? globalThis.fetch)(url, {
      method: config.method, headers, body, signal: config.signal,
      credentials: 'same-origin', redirect: 'error',
    });
    if (EMPTY_STATUSES.has(response.status) && response.ok) {
      return { data: undefined, error: undefined, response };
    }
    const mediaType = response.headers.get('Content-Type')?.split(';')[0]?.trim().toLowerCase();
    if (mediaType !== JSON_TYPE && !mediaType?.endsWith('+json')) {
      throw new ApiProtocolError(`API returned a non-JSON response (${response.status}).`, response);
    }
    let data: unknown;
    try { data = await response.json(); }
    catch { throw new ApiProtocolError(`API returned invalid JSON (${response.status}).`, response); }
    if (response.ok) {
      if (TOKEN_ENDPOINTS.has(url.pathname) && record(data) && typeof data.csrf_token === 'string' && data.csrf_token) {
        csrfToken = data.csrf_token;
      }
      return { data, error: undefined, response };
    }
    if (!errorEnvelope(data)) throw new ApiProtocolError(`API returned an unrecognized error (${response.status}).`, response);
    if (data.error.code === 'csrf_failed') csrfToken = null;
    if (config.throwOnError ?? true) throw new ApiError(data, response);
    return { data: undefined, error: data, response };
  };
  return Object.assign(request, {
    setCsrfToken(token: string | null) {
      if (token !== null && !token.trim()) throw new TypeError('CSRF token must be nonempty.');
      csrfToken = token;
    },
    clearCsrfToken() { csrfToken = null; },
    getCsrfToken() { return csrfToken; },
  });
}

// No DOM access or requests on import; browser origin is resolved only on a call.
export const client = createApiClient();
