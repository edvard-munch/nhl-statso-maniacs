import { afterEach, describe, expect, it, vi } from 'vitest';
afterEach(() => vi.unstubAllGlobals());
import {
  authCsrfRetrieve,
  authLoginCreate,
  authLogoutCreate,
  authRegisterCreate,
  meAccountImagePut,
  meAccountPatch,
  meFavoriteDelete,
  meFavoritePut,
  playerRetrieve,
  playersList,
  scoreboardList,
} from '../src/api/generated/sdk.js';
import {
  ApiError,
  ApiProtocolError,
  createApiClient,
  CsrfTokenRequiredError,
} from '../src/api/http.js';

const ORIGIN = 'https://nhl.example.test';
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'test-correlation' },
  });
}
function setup(...responses: Response[]) {
  const calls: Array<{ url: URL; init: RequestInit }> = [];
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = new URL(String(input));
    calls.push({ url, init: init ?? {} });
    const response = responses.shift();
    if (!response) throw new Error('Unexpected HTTP request');
    Object.defineProperty(response, 'url', { value: url.href });
    return response;
  });
  return { api: createApiClient({ origin: ORIGIN, fetch }), calls, fetch };
}
const failure = {
  error: {
    code: 'invalid_parameters',
    message: 'Check the fields.',
    fields: { username: ['Already used.'] },
  },
};

describe('generated operations and Django transport', () => {
  it('serializes literal Unicode/CSV queries, zero and false without dropping them', async () => {
    const { api, calls } = setup(json({ results: [], count: 0 }));
    await playersList({
      client: api,
      query: {
        season_id: '20262027',
        search: 'L’Heureux & +',
        team: 'BUF,COL',
        goals_min: 0,
        rookie: false,
        page_size: 1,
      },
    });
    const { url, init } = calls[0]!;
    expect(url.pathname).toBe('/api/v1/players/');
    expect(url.searchParams.get('search')).toBe('L’Heureux & +');
    expect(url.searchParams.get('team')).toBe('BUF,COL');
    expect(url.searchParams.get('goals_min')).toBe('0');
    expect(url.searchParams.get('rookie')).toBe('false');
    expect(init.credentials).toBe('same-origin');
    expect(init.redirect).toBe('error');
    expect(new Headers(init.headers).get('Accept')).toBe('application/json');
    expect(new Headers(init.headers).has('Cookie')).toBe(false);
    expect(new Headers(init.headers).has('Authorization')).toBe(false);
    expect(new Headers(init.headers).has('X-CSRFToken')).toBe(false);
  });

  it('encodes typed path parameters independently of URL syntax', async () => {
    const { api, calls } = setup(json({}));
    await playerRetrieve({ client: api, path: { player_type: 'skater', nhl_id: 8482076 } });
    expect(calls[0]!.url.pathname).toBe('/api/v1/players/skater/8482076/');
    await expect(
      api({
        method: 'GET',
        url: '/api/v1/players/{player_type}/{nhl_id}/',
        path: { player_type: 'skater' },
      }),
    ).rejects.toThrow('Missing path parameter');
    expect(calls).toHaveLength(1);
  });

  it('bootstraps CSRF through the SDK and replaces the token after login/logout', async () => {
    const { api, calls } = setup(
      json({ csrf_token: 'bootstrap-token' }),
      json({
        authenticated: true,
        csrf_token: 'login-token',
        user: { id: 1, username: 'example' },
      }),
      json({ authenticated: false, csrf_token: 'logout-token', user: null }),
    );
    await authCsrfRetrieve({ client: api });
    await authLoginCreate({
      client: api,
      body: { username: 'example', password: '  preserved whitespace  ' },
    });
    expect(api.getCsrfToken()).toBe('login-token');
    await authLogoutCreate({ client: api });
    expect(calls.slice(1).map((call) => new Headers(call.init.headers).get('X-CSRFToken'))).toEqual(
      ['bootstrap-token', 'login-token'],
    );
    expect(JSON.parse(String(calls[1]!.init.body))).toEqual({
      username: 'example',
      password: '  preserved whitespace  ',
    });
    expect(api.getCsrfToken()).toBe('logout-token');
    api.clearCsrfToken();
    expect(api.getCsrfToken()).toBeNull();
  });

  it('does not send anonymous login/registration or private mutations without CSRF', async () => {
    const { api, fetch } = setup();
    await expect(
      authLoginCreate({ client: api, body: { username: 'example', password: 'secret' } }),
    ).rejects.toBeInstanceOf(CsrfTokenRequiredError);
    await expect(
      authRegisterCreate({
        client: api,
        body: {
          username: 'example',
          email: 'example@example.invalid',
          password1: 'a',
          password2: 'a',
        },
      }),
    ).rejects.toBeInstanceOf(CsrfTokenRequiredError);
    await expect(
      meFavoritePut({ client: api, path: { player_type: 'skater', nhl_id: 1 } }),
    ).rejects.toBeInstanceOf(CsrfTokenRequiredError);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('uses an explicitly supplied token before bootstrap and the held rotated token afterward', async () => {
    const { api, calls } = setup(json({}), json({}));
    await meAccountPatch({
      client: api,
      headers: { 'X-CSRFToken': 'explicit' },
      body: { email: 'new@example.invalid' },
    });
    api.setCsrfToken('rotated');
    await meAccountPatch({
      client: api,
      headers: { 'X-CSRFToken': 'stale' },
      body: { email: 'other@example.invalid' },
    });
    expect(calls.map((call) => new Headers(call.init.headers).get('X-CSRFToken'))).toEqual([
      'explicit',
      'rotated',
    ]);
    expect(() => api.setCsrfToken(' ')).toThrow(TypeError);
  });

  it('keeps token state isolated between client instances', async () => {
    const first = setup(json({}));
    const second = setup();
    first.api.setCsrfToken('first');
    await meFavoritePut({ client: first.api, path: { player_type: 'skater', nhl_id: 1 } });
    await expect(
      meFavoritePut({ client: second.api, path: { player_type: 'skater', nhl_id: 1 } }),
    ).rejects.toBeInstanceOf(CsrfTokenRequiredError);
    expect(second.fetch).not.toHaveBeenCalled();
  });

  it('sends image files as multipart with the filename and browser-generated boundary', async () => {
    const { api, calls } = setup(json({}));
    api.setCsrfToken('token');
    const file = new File([new Uint8Array([1, 2, 3])], 'avatar.png', { type: 'image/png' });
    await meAccountImagePut({ client: api, body: { image: file } });
    const init = calls[0]!.init;
    expect(init.body).toBeInstanceOf(FormData);
    const image = (init.body as FormData).get('image') as File;
    expect(image.name).toBe('avatar.png');
    expect(await image.arrayBuffer()).toEqual(await file.arrayBuffer());
    expect(new Headers(init.headers).has('Content-Type')).toBe(false);
    expect(new Headers(init.headers).get('X-CSRFToken')).toBe('token');
  });

  it('preserves an existing FormData body and removes manually set boundary headers', async () => {
    const { api, calls } = setup(json({}));
    api.setCsrfToken('token');
    const form = new FormData();
    form.set('image', new Blob(['image']));
    await api({
      method: 'PUT',
      url: '/api/v1/me/image/',
      body: form,
      headers: { 'Content-Type': 'multipart/form-data; boundary=wrong' },
    });
    expect(calls[0]!.init.body).toBe(form);
    expect(new Headers(calls[0]!.init.headers).has('Content-Type')).toBe(false);
  });

  it('handles contentless DELETE without parsing JSON or inventing a body', async () => {
    const response = new Response(null, { status: 204 });
    const parse = vi.spyOn(response, 'json');
    const { api, calls } = setup(response);
    api.setCsrfToken('token');
    const result = await meFavoriteDelete({
      client: api,
      path: { player_type: 'goalie', nhl_id: 1 },
    });
    expect(result.data).toBeUndefined();
    expect(result.error).toBeUndefined();
    expect(parse).not.toHaveBeenCalled();
    expect(calls[0]!.init.body).toBeUndefined();
  });

  it('returns typed JSON errors when throwing is disabled', async () => {
    const { api } = setup(json(failure, 400));
    const result = await playersList({ client: api, throwOnError: false });
    expect(result.data).toBeUndefined();
    expect(result.error?.error.code).toBe('invalid_parameters');
    expect(result.error?.error.fields).toEqual(failure.error.fields);
  });

  it('throws structured errors with correlation ID without retrying a mutation', async () => {
    const { api, fetch } = setup(json(failure, 409));
    api.setCsrfToken('token');
    const error = await meFavoritePut({
      client: api,
      path: { player_type: 'skater', nhl_id: 1 },
    }).catch((error) => error);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.body).toEqual(failure);
    expect(error.response.status).toBe(409);
    expect(error.requestId).toBe('test-correlation');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('clears a rejected CSRF token and requires explicit recovery without replaying the write', async () => {
    const { api, fetch } = setup(
      json({ error: { code: 'csrf_failed', message: 'CSRF failed.' } }, 403),
    );
    api.setCsrfToken('old');
    await expect(
      meFavoritePut({ client: api, path: { player_type: 'skater', nhl_id: 1 } }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(api.getCsrfToken()).toBeNull();
    await expect(
      meFavoritePut({ client: api, path: { player_type: 'skater', nhl_id: 1 } }),
    ).rejects.toBeInstanceOf(CsrfTokenRequiredError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([200, 403, 502])(
    'rejects HTML/proxy output at status %s without exposing its text',
    async (status) => {
      const { api } = setup(
        new Response('<html>private server details</html>', {
          status,
          headers: { 'Content-Type': 'text/html' },
        }),
      );
      const error = await playersList({ client: api, throwOnError: false }).catch((error) => error);
      expect(error).toBeInstanceOf(ApiProtocolError);
      expect(error.message).not.toContain('private server details');
    },
  );

  it.each([
    '{broken',
    '{}',
    '{"error":{"code":12,"message":"bad"}}',
    '{"error":{"code":"bad","message":"bad","fields":"bad"}}',
  ])('rejects malformed error envelopes: %s', async (body) => {
    const { api } = setup(
      new Response(body, { status: 500, headers: { 'Content-Type': 'application/json' } }),
    );
    await expect(playersList({ client: api })).rejects.toBeInstanceOf(ApiProtocolError);
  });

  it('propagates cancellation and network failures without wrapping or retrying', async () => {
    const abort = new DOMException('Stopped', 'AbortError');
    const fetch = vi.fn<typeof globalThis.fetch>(async (_, init) => {
      init?.signal?.throwIfAborted();
      throw abort;
    });
    const api = createApiClient({ origin: ORIGIN, fetch });
    const controller = new AbortController();
    controller.abort(abort);
    await expect(playersList({ client: api, signal: controller.signal })).rejects.toBe(abort);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('follows encoded same-origin pagination URLs without changing their filters', async () => {
    const next = `${ORIGIN}/api/v1/players/?page=2&search=L%E2%80%99Heureux+%26+%2B&team=BUF%2CCOL`;
    const { api, calls } = setup(
      json({ count: 2, next, previous: null, results: [], meta: {} }),
      json({ count: 2, next: null, results: [], meta: {} }),
    );
    const first = await playersList({
      client: api,
      query: { search: 'L’Heureux & +', team: 'BUF,COL', page_size: 1 },
    });
    await api({ method: 'GET', url: first.data.next! });
    expect(calls[1]!.url.searchParams.get('page')).toBe('2');
    expect(calls[1]!.url.searchParams.get('search')).toBe('L’Heureux & +');
    expect(calls[1]!.url.searchParams.get('team')).toBe('BUF,COL');
  });

  it.each([
    'https://other.example/api/v1/me/',
    '//other.example/api/v1/me/',
    '/admin/',
    '/api/v1/../../admin/',
    '/api/v1/players/#fragment',
    'https://user:password@nhl.example.test/api/v1/me/',
  ])('rejects foreign or non-API URLs before requests: %s', async (url) => {
    const { api, fetch } = setup();
    api.setCsrfToken('secret-token');
    await expect(api({ method: 'POST', url })).rejects.toThrow(TypeError);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps saved state/null statistics unchanged instead of transforming JSON', async () => {
    const payload = {
      count: 1,
      next: null,
      previous: null,
      meta: {},
      results: [
        {
          state: { value: 'unknown', source: null, observed_at: null, conflict: true },
          away_score: 0,
          home_score: null,
        },
      ],
    };
    const { api } = setup(json(payload));
    const result = await scoreboardList({ client: api, query: { date: '2026-11-11' } });
    expect(result.data).toEqual(payload);
  });
});

it('rejects an origin override that differs from the actual browser origin', async () => {
  vi.stubGlobal('location', { origin: ORIGIN });
  const fetch = vi.fn<typeof globalThis.fetch>();
  const api = createApiClient({ origin: 'https://other.example', fetch });
  api.setCsrfToken('secret-token');
  await expect(
    meFavoritePut({ client: api, path: { player_type: 'skater', nhl_id: 1 } }),
  ).rejects.toThrow('browser origin');
  expect(fetch).not.toHaveBeenCalled();
});

it('propagates network errors on unsafe requests without retrying', async () => {
  const failure = new TypeError('Failed to fetch');
  const fetch = vi.fn<typeof globalThis.fetch>().mockRejectedValue(failure);
  const api = createApiClient({ origin: ORIGIN, fetch });
  api.setCsrfToken('token');
  await expect(
    meFavoritePut({ client: api, path: { player_type: 'skater', nhl_id: 1 } }),
  ).rejects.toBe(failure);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(api.getCsrfToken()).toBe('token');
});
