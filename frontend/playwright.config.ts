import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(frontendRoot, '..');
const python = process.env.PYTHON_EXE ?? path.join(projectRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

export default defineConfig({
  testDir: './tests',
  globalTeardown: './tests/auth-teardown.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:15173',
    browserName: 'chromium',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `"${python}" -m testing.browser_auth_server`,
      cwd: projectRoot,
      url: 'http://127.0.0.1:18003/api/v1/health',
      reuseExistingServer: false,
      env: { PYTHONPATH: 'backend', APP_ENV: 'test', FRONTEND_ORIGIN: 'http://127.0.0.1:15173',
        AUTH_COOKIE_SECURE: 'false', AUTH_COOKIE_SAME_SITE: 'lax' },
    },
    {
      command: process.env.FRONTEND_PREVIEW === '1' ? 'npm run preview -- --port 15173 --strictPort' : 'npm run dev -- --port 15173 --strictPort',
      cwd: frontendRoot,
      url: 'http://127.0.0.1:15173',
      reuseExistingServer: false,
      env: { VITE_API_URL: 'http://127.0.0.1:18003' },
    },
  ],
});
