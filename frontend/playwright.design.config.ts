import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = path.dirname(fileURLToPath(import.meta.url));

/** Deterministic frontend journeys use fixture APIs and the production bundle. */
export default defineConfig({
  testDir: './tests',
  testMatch: [
    'product-design.spec.ts', 'page-actions.spec.ts', 'renovation-page-system.spec.ts',
    'renovation-tabs.spec.ts', 'renovation-navigation.spec.ts',
    'renovation-dialog.spec.ts', 'renovation-mobile-chat.spec.ts',
    'renovation-side-panel.spec.ts', 'renovation-performance.spec.ts',
    'renovation-composer-add.spec.ts',
    'renovation-chat-welcome.spec.ts',
  ],
  fullyParallel: false, workers: 1, timeout: 60000,
  expect: { timeout: 6000 },
  use: {
    baseURL: 'http://127.0.0.1:15173', browserName: 'chromium',
    trace: 'retain-on-failure', screenshot: 'only-on-failure',
  },
  outputDir: './test-results/product-design',
  webServer: {
    command: 'npm run preview -- --port 15173 --strictPort', cwd: frontend,
    url: 'http://127.0.0.1:15173', reuseExistingServer: false, timeout: 60000,
  },
});
