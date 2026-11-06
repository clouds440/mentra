import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests', testMatch: ['assessment-handoff.spec.ts', 'quiz-local.spec.ts','assessment-design.spec.ts','learning-observations.spec.ts','assessment-live.spec.ts'],
  workers: 1, timeout: 30_000,
  reporter: [['list'], ['json', { outputFile: '../.implementation/phase7-browser.json' }]],
  use: { baseURL: 'http://127.0.0.1:15188', browserName: 'chromium', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: `node node_modules/vite/bin/vite.js ${process.env.ASSESSMENT_PREVIEW === '1' ? 'preview' : ''} --configLoader runner --host 127.0.0.1 --port 15188 --strictPort`,
    url: 'http://127.0.0.1:15188', reuseExistingServer: false },
});
