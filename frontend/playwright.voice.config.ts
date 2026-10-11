import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: 'voice.spec.ts', workers: 1,
  use: { baseURL: 'http://127.0.0.1:15174', browserName: 'chromium', screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --port 15174 --strictPort', url: 'http://127.0.0.1:15174', reuseExistingServer: false },
});
