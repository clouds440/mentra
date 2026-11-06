import { defineConfig } from '@playwright/test';

// Start testing.browser_auth_server on 18003 against TEST_DATABASE_URL first.
// It owns a disposable schema, real API/services and deterministic model/file substitutes.
export default defineConfig({
  testDir:'./tests',testMatch:['answer-sheet-flow.spec.ts','chat-assessments.spec.ts',
    'learning-topics.spec.ts','renovation-assessments.spec.ts','renovation-answer-sheets.spec.ts',
    'chat-interactions.spec.ts','chat-questionnaire.spec.ts','orchestration.spec.ts'],
  workers:1,timeout:30_000,globalTeardown:'./tests/auth-teardown.ts',
  outputDir:'../.implementation/browser-integration-artifacts',
  reporter:[['list'],['json',{outputFile:'../.implementation/integrated-browser.json'}]],
  use:{baseURL:'http://127.0.0.1:15173',browserName:'chromium',trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:{command:'node node_modules/vite/bin/vite.js preview --configLoader runner --host 127.0.0.1 --port 15173 --strictPort',
    url:'http://127.0.0.1:15173',reuseExistingServer:false},
});
