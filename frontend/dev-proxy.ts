import type { ProxyOptions } from 'vite';

export const DEFAULT_DJANGO_ORIGIN = 'http://127.0.0.1:8000';
export const DEV_HOST = '127.0.0.1';
export const DEV_PORT = 5173;
export const PREVIEW_PORT = 4173;
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

export function createDevProxy(target = DEFAULT_DJANGO_ORIGIN): Record<string, ProxyOptions> {
  const url = new URL(target);
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    !LOOPBACK_HOSTS.has(url.hostname) ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      'DJANGO_DEV_ORIGIN must be a loopback HTTP(S) origin without credentials or a path.',
    );
  }
  // Preserve Host and Origin together: Django sees the browser's same origin for CSRF.
  const options: ProxyOptions = { target: url.origin, changeOrigin: false, xfwd: false };
  return { '^/api/v1(?:/|$)': { ...options }, '^/media/': { ...options } };
}
