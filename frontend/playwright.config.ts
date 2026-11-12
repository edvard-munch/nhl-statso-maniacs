import { defineConfig } from '@playwright/test';
import { DEV_HOST, PREVIEW_PORT } from './dev-proxy.js';

const BASE_URL = `http://${DEV_HOST}:${PREVIEW_PORT}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  use: { baseURL: BASE_URL, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1280, height: 800 } } },
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        viewport: { width: 360, height: 780 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: {
    command: 'corepack pnpm preview',
    url: BASE_URL,
    reuseExistingServer: false,
  },
});
