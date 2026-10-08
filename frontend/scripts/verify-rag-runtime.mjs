// Browser verification of the built Nginx frontend against isolated production API/worker processes.
import { chromium, expect } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const sourceBytes = Buffer.from('Python decorators wrap functions to add reusable behavior and logging.');
try {
  await page.goto('http://127.0.0.1:15174/register');
  await page.getByLabel('Username', { exact: true }).fill(`prod_rag_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('isolated production browser passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Make Mentra yours' })).toBeVisible();
  await page.getByLabel('Education level', { exact: true }).selectOption('undergraduate');
  await page.getByLabel('Field or area of study', { exact: true }).fill('Computer science');
  await page.getByLabel('Primary learning goal', { exact: true }).fill('Understand Python programming');
  await page.getByLabel('Learning preference', { exact: true }).selectOption('examples_first');
  await page.getByLabel('Explanation depth', { exact: true }).selectOption('standard');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.getByRole('button', { name: 'Skip for now', exact: true }).click();
  await expect(page).toHaveURL('http://127.0.0.1:15174/');
  await page.goto('http://127.0.0.1:15174/library');
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'production-notes.txt', mimeType: 'text/plain', buffer: sourceBytes });
  await page.getByLabel('Material title', { exact: true }).fill('Production browser notes');
  await page.getByLabel('New context name', { exact: true }).fill('Python');
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Study in chat', exact: true })).toBeVisible({ timeout: 30_000 });
  await page.reload();
  await page.getByRole('link', { name: 'Study in chat', exact: true }).click();
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Explain decorators from my notes');
  await page.getByRole('button', { name: 'Send message' }).click();
  await page.getByRole('button', { name: 'Open cited source Production browser notes' }).click();
  await expect(page.getByRole('dialog')).toContainText('Python decorators wrap functions');
  await expect(page.getByRole('dialog').locator('section')).toHaveCount(1);
  const sourceBounds = await page.getByRole('dialog').boundingBox();
  expect(Math.abs(sourceBounds.y + sourceBounds.height / 2 - 450)).toBeLessThan(2);
  await page.screenshot({ path: fileURLToPath(new URL('../../docs/rag-production-browser.png', import.meta.url)), fullPage: true });
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download original' }).click();
  const download = await pending;
  expect(await readFile(await download.path())).toEqual(sourceBytes);
  await page.keyboard.press('Escape');
  await page.goto('http://127.0.0.1:15174/library');
  await page.getByRole('link', { name: 'Production browser notes', exact: true }).click();
  await expect(page).toHaveURL(/\/library\/[^/]+$/);
  await page.reload();
  await expect(page.getByText('Ready to study', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Delete material', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Production browser notes', exact: true })).toHaveCount(0);
  console.log(JSON.stringify({ built_frontend: true, nginx_spa_routes: true, authenticated_upload: true,
    real_embedding_ingestion: true, citation_dialog: true, authenticated_original_download: true, deletion: true }));
} finally {
  await context.close(); await browser.close();
}
