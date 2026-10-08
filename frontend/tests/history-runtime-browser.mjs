// Runs against rebuilt Nginx/API images using only a disposable test account.
// Redirect compiled API URLs to the isolated API; never contact an application DB.
import { chromium, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 960 }, colorScheme: 'light' });
  const page = await context.newPage();
  await page.route('**/api/v1/**', async route => {
    const original = new URL(route.request().url());
    const response = await route.fetch({ url: `http://127.0.0.1:18401${original.pathname}${original.search}`,
      headers: { ...route.request().headers(), Cookie: process.env.HISTORY_RUNTIME_COOKIE, Origin: 'http://127.0.0.1:15174' } });
    await route.fulfill({ response });
  });
  await page.goto('http://127.0.0.1:15174/settings?tab=memories');
  await expect(page.getByRole('tab', { name: 'Memories' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('button', { name: 'Add memory', exact: true }).click();
  await page.getByRole('textbox', { name: 'Memory', exact: true }).fill('I prefer production image verification.');
  await page.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByText('I prefer production image verification.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('I prefer production image verification.', { exact: true })).toBeVisible();
  const output = path.resolve('frontend/test-results');
  mkdirSync(output, { recursive: true });
  await page.screenshot({ path: path.join(output, 'history-runtime-settings.png'), animations: 'disabled' });
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(page.getByRole('alertdialog', { name: 'Delete memory' })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.getByText('A fresh start')).toBeVisible();
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Remember that I prefer annotated diagrams.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('article', { name: 'Mentra response' }).last()).toContainText('saved');
  await page.goto('http://127.0.0.1:15174/settings?tab=memories');
  await expect(page.getByRole('region', { name: 'Memories', exact: true }).getByText('Remember that I prefer annotated diagrams.', { exact: true })).toBeVisible();
  console.log('Rebuilt Nginx browser UI: manual CRUD, refresh persistence, native confirmation dialog and actual tool-written memory verified.');
} finally {
  await browser.close();
}
