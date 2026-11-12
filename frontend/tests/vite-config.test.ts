import { expect, it, vi } from 'vitest';
import configure from '../vite.config.js';
import { DEV_HOST, DEV_PORT } from '../dev-proxy.js';

it('keeps the backend target server-only and disables inherited proxying in preview', () => {
  vi.stubEnv('DJANGO_DEV_ORIGIN', 'http://localhost:8999');
  try {
    const config = configure({ command: 'serve', mode: 'test' });
    expect(config.server).toMatchObject({ host: DEV_HOST, port: DEV_PORT, strictPort: true });
    expect(config.server?.proxy?.['^/api/v1(?:/|$)']).toMatchObject({
      target: 'http://localhost:8999',
      changeOrigin: false,
    });
    expect(config.preview?.proxy).toEqual({});
    expect(config.define).toBeUndefined();
  } finally {
    vi.unstubAllEnvs();
  }
});
