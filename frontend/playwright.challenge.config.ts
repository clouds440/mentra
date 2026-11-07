import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'./tests',testMatch:['challenge-preferences.spec.ts','assessment-design.spec.ts','assessment-handoff.spec.ts','quiz-local.spec.ts','learning-observations.spec.ts','renovation-live-visuals.spec.ts'],
  workers:1,timeout:30000,outputDir:'../.implementation/challenge-browser-artifacts',
  reporter:[['list'],['json',{outputFile:'../.implementation/challenge-browser.json'}]],
  use:{baseURL:'http://127.0.0.1:15188',browserName:'chromium',trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:{command:'node node_modules/vite/bin/vite.js preview --configLoader runner --host 127.0.0.1 --port 15188 --strictPort',url:'http://127.0.0.1:15188',reuseExistingServer:false},
});
