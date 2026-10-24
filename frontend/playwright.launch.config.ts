// Dedicated local TLS drill against already-running disposable launch-gate services.
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: 'launch-https.spec.ts',
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: 'https://front.launchgate.example.org:19443',
    ignoreHTTPSErrors: true, // Self-signed, one-day local drill certificate only.
    browserName: 'chromium',
    launchOptions: { args: ['--no-proxy-server', '--host-resolver-rules=MAP front.launchgate.example.org 127.0.0.1, MAP api.launchgate.example.org 127.0.0.1'] },
    trace: 'retain-on-failure',
  },
});
