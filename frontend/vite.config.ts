import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import { createDevProxy, DEV_HOST, DEV_PORT, PREVIEW_PORT } from './dev-proxy.js';

const ROOT = fileURLToPath(new URL('./', import.meta.url));

export default defineConfig(({ mode }) => {
  // Server-only option. Do not expose a backend URL or secrets through VITE_*.
  const env = loadEnv(mode, ROOT, 'DJANGO_DEV_');
  return {
    plugins: [vue()],
    server: {
      host: DEV_HOST,
      port: DEV_PORT,
      strictPort: true,
      proxy: createDevProxy(process.env.DJANGO_DEV_ORIGIN ?? env.DJANGO_DEV_ORIGIN),
    },
    preview: { host: DEV_HOST, port: PREVIEW_PORT, strictPort: true, proxy: {} },
    build: { sourcemap: false },
  };
});
