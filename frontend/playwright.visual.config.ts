import { defineConfig } from '@playwright/test';

// UI-only fixtures deliberately intercept APIs; domain suites use the main config.
export default defineConfig({
  testDir: './tests',
  testMatch: ['renovation*.spec.ts'],
  workers: 1,
  timeout: 30_000,
  use: { baseURL: process.env.FRONTEND_VISUAL_URL ?? 'http://127.0.0.1:15174', browserName: 'chromium', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: process.env.FRONTEND_VISUAL_URL ? undefined : { command: process.env.FRONTEND_VISUAL_DEV === '1' ? 'npm run dev -- --port 15174 --strictPort' : process.env.FRONTEND_VISUAL_BASELINE === '1' ? 'npm run preview -- --outDir test-results/renovation-original-dist --port 15174 --strictPort' : 'npm run preview -- --port 15174 --strictPort', url: 'http://127.0.0.1:15174', reuseExistingServer: false },
});
