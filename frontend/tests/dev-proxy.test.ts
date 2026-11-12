import { afterAll, beforeAll, expect, it } from 'vitest';
import { createServer as createHttpServer, type Server } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { fileURLToPath } from 'node:url';
import { createServer, type ViteDevServer } from 'vite';
import { createDevProxy, DEV_HOST } from '../dev-proxy.js';
import { authCsrfRetrieve, authLoginCreate } from '../src/api/generated/sdk.js';
import { createApiClient } from '../src/api/http.js';

const seen: Array<{
  url: string;
  host: string | undefined;
  origin: string | undefined;
  cookie: string | undefined;
  token: string | undefined;
  body: string;
}> = [];
let backend: Server;
let vite: ViteDevServer;
let origin: string;

beforeAll(async () => {
  backend = createHttpServer(async (request, response) => {
    let body = '';
    for await (const chunk of request) body += chunk;
    seen.push({
      url: request.url!,
      host: request.headers.host,
      origin: request.headers.origin,
      cookie: request.headers.cookie,
      token: request.headers['x-csrftoken'] as string | undefined,
      body,
    });
    if (request.url === '/media/avatar.bin') {
      response.writeHead(200, { 'Content-Type': 'application/octet-stream' });
      response.end(Buffer.from([0, 128, 255]));
    } else if (request.url === '/api/v1/auth/csrf/') {
      response.writeHead(200, {
        'Content-Type': 'application/json',
        'Set-Cookie': 'csrftoken=initial; Path=/; SameSite=Lax; HttpOnly',
      });
      response.end(JSON.stringify({ csrf_token: 'initial' }));
    } else if (request.url === '/api/v1/auth/login/') {
      const valid =
        request.headers.origin === `http://${request.headers.host}` &&
        request.headers.cookie === 'csrftoken=initial' &&
        request.headers['x-csrftoken'] === 'initial';
      response.writeHead(valid ? 200 : 403, {
        'Content-Type': 'application/json',
        'Set-Cookie': 'sessionid=session; Path=/; SameSite=Lax; HttpOnly',
      });
      response.end(
        JSON.stringify(
          valid
            ? { csrf_token: 'rotated', authenticated: true }
            : { error: { code: 'csrf_failed', message: 'Rejected' } },
        ),
      );
    } else {
      response.writeHead(503, { 'Content-Type': 'text/html', 'Retry-After': '3' });
      response.end('<h1>Unavailable</h1>');
    }
  });
  backend.listen(0, DEV_HOST);
  await once(backend, 'listening');
  const target = `http://${DEV_HOST}:${(backend.address() as AddressInfo).port}`;
  vite = await createServer({
    configFile: false,
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: {
      host: DEV_HOST,
      port: 0,
      strictPort: false,
      proxy: createDevProxy(target),
      watch: null,
    },
    logLevel: 'silent',
  });
  await vite.listen();
  origin = `http://${DEV_HOST}:${(vite.httpServer!.address() as AddressInfo).port}`;
});
afterAll(async () => {
  await vite?.close();
  if (backend?.listening) {
    backend.closeAllConnections();
    await new Promise<void>((resolve) => backend.close(() => resolve()));
  }
});

it('passes same-origin Host, Origin, cookies, CSRF and JSON bodies through the real proxy', async () => {
  const browserFetch: typeof fetch = async (input, init) => {
    const headers = new Headers(init?.headers);
    headers.set('Origin', origin);
    headers.set('Cookie', 'csrftoken=initial');
    return fetch(input, { ...init, headers });
  };
  const client = createApiClient({ origin, fetch: browserFetch });
  const bootstrap = await authCsrfRetrieve({ client });
  expect(bootstrap.response.headers.get('set-cookie')).toBe(
    'csrftoken=initial; Path=/; SameSite=Lax; HttpOnly',
  );
  const result = await authLoginCreate({
    client,
    body: { username: 'test', password: ' unchanged ' },
  });
  expect(result.response.headers.get('set-cookie')).toContain('sessionid=session; Path=/');
  expect(client.getCsrfToken()).toBe('rotated');
  expect(seen.at(-1)).toMatchObject({
    host: new URL(origin).host,
    origin,
    cookie: 'csrftoken=initial',
    token: 'initial',
  });
  expect(JSON.parse(seen.at(-1)!.body)).toEqual({ username: 'test', password: ' unchanged ' });
});

it('preserves media bytes and upstream error status, headers and non-JSON content', async () => {
  const media = await fetch(`${origin}/media/avatar.bin`);
  expect([...new Uint8Array(await media.arrayBuffer())]).toEqual([0, 128, 255]);
  const path = '/api/v1/missing?search=L%E2%80%99Heureux%20%26%20%2B';
  const failed = await fetch(`${origin}${path}`);
  expect(seen.at(-1)!.url).toBe(path);
  expect(failed.status).toBe(503);
  expect(failed.headers.get('retry-after')).toBe('3');
  expect(failed.headers.get('content-type')).toBe('text/html');
  expect(await failed.text()).toBe('<h1>Unavailable</h1>');
});

it('keeps SPA routes and lookalike API paths out of the Django proxy', async () => {
  const count = seen.length;
  for (const pathname of ['/missing/route', '/api/v10/not-an-api', '/players/']) {
    const response = await fetch(`${origin}${pathname}`, { headers: { Accept: 'text/html' } });
    expect(response.status).toBe(200);
    expect(await response.text()).toContain('<div id="app">');
  }
  expect(seen).toHaveLength(count);
});

it.each([
  'https://example.com',
  'http://user:password@localhost:8000',
  'file:///tmp',
  'http://localhost:8000/api/',
  'http://localhost:8000?target=x',
])('rejects unsafe or ambiguous dev target %s', (target) => {
  expect(() => createDevProxy(target)).toThrow('loopback HTTP(S) origin');
});
