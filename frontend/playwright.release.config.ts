import {defineConfig} from '@playwright/test';
const productionFiles=['assessment-design.spec.ts','assessment-live.spec.ts','challenge-preferences.spec.ts','quiz-local.spec.ts','learning-observations.spec.ts','renovation-live-visuals.spec.ts','product-design.spec.ts','page-actions.spec.ts','renovation-rich-chat.spec.ts','renovation-recharts.spec.ts','renovation-rich-performance.spec.ts','renovation-smart-tools.spec.ts'];
const performanceFiles=['assessment-handoff.spec.ts','renovation-performance.spec.ts'];
export default defineConfig({
  testDir:'./tests',fullyParallel:false,workers:4,timeout:60000,expect:{timeout:6000},
  projects:[
    {name:'journeys',testIgnore:[...productionFiles,...performanceFiles]},
    {name:'production',testMatch:productionFiles,workers:4,use:{baseURL:'http://127.0.0.1:15188'}},
    {name:'performance',testMatch:performanceFiles,workers:1,dependencies:['production'],use:{baseURL:'http://127.0.0.1:15188'}},
  ],
  globalTeardown:'./tests/auth-teardown.ts',outputDir:'../.implementation/full-frontend-release-artifacts',
  reporter:[['list'],['json',{outputFile:'../.implementation/full-frontend-release.json'}]],
  use:{baseURL:'http://127.0.0.1:15173',browserName:'chromium',trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:[
    {command:'node node_modules/vite/bin/vite.js --configLoader runner --host 127.0.0.1 --port 15173 --strictPort',url:'http://127.0.0.1:15173',reuseExistingServer:false,env:{VITE_API_URL:'http://127.0.0.1:18003'}},
    {command:'node node_modules/vite/bin/vite.js preview --configLoader runner --host 127.0.0.1 --port 15188 --strictPort',url:'http://127.0.0.1:15188',reuseExistingServer:false},
  ],
});
