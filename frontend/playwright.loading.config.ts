import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', testMatch: 'loading.spec.ts', workers: 1,
  use: { baseURL: 'http://127.0.0.1:15175', browserName: 'chromium', screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --port 15175 --strictPort', url: 'http://127.0.0.1:15175', reuseExistingServer: false },
});
