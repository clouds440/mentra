import { test, expect } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

test('Library source originals download unchanged on desktop and another signed-in mobile session', async ({ page, browser }) => {
  const username = `files_${randomUUID().slice(0, 8)}`;
  const password = 'FilesTesting123!';
  const original = Buffer.from('export const answer: number = 42;\r\n// Original source bytes\r\n');
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await page.goto('/library/new');
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'example.ts', mimeType: 'text/typescript', buffer: original });
  await page.getByLabel('Material title', { exact: true }).fill('Original code');
  await page.getByLabel('New context name', { exact: true }).fill('Programming');
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page).toHaveURL(/\/library\?uploaded=accepted$/, { timeout: 90_000 });
  await page.getByRole('link', { name: 'Original code', exact: true }).click();
  const materialUrl = page.url();
  await expect(page.getByRole('button', { name: 'Open source version' })).toBeEnabled({ timeout: 90_000 });
  await page.getByRole('button', { name: 'Open source version' }).click();
  const dialog = page.getByRole('dialog', { name: 'Source: Original code' });
  await expect(dialog).toBeVisible();
  const desktopDownload = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Download original' }).click();
  const desktop = await desktopDownload;
  expect(desktop.suggestedFilename()).toBe('example.ts');
  expect(await readFile((await desktop.path())!)).toEqual(original);

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
  try {
    const other = await mobile.newPage();
    await other.goto('/login');
    await other.getByLabel('Username', { exact: true }).fill(username);
    await other.getByLabel('Password', { exact: true }).fill(password);
    await other.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(other).not.toHaveURL(/\/login/);
    await other.goto(materialUrl);
    await other.getByRole('button', { name: 'Open source version' }).click();
    const mobileDownload = other.waitForEvent('download');
    await other.getByRole('dialog').getByRole('button', { name: 'Download original' }).click();
    const downloaded = await mobileDownload;
    expect(downloaded.suggestedFilename()).toBe('example.ts');
    expect(await readFile((await downloaded.path())!)).toEqual(original);
  } finally {
    await mobile.close();
  }
});
