import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests', testMatch: ['chat-images.spec.ts', 'workspace-polish.spec.ts'],
  workers: 1, timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:15174', browserName: 'chromium', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --port 15174 --strictPort', url: 'http://127.0.0.1:15174', reuseExistingServer: false },
});
