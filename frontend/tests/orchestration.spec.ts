import { chooseOption } from './select-helpers';
import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

test('chat file extraction and explicit Library admission survive reload', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`files_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('a unique attachment test passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  const created = await page.request.post('http://127.0.0.1:18003/api/v1/learning-contexts', {
    headers: { Origin: 'http://127.0.0.1:15173' }, data: { name: 'Biology', activate: true },
  });
  expect(created.ok()).toBeTruthy();
  const context = await created.json();
  await page.getByLabel('Upload chat files').setInputFiles({ name: 'biology.txt', mimeType: 'text/plain', buffer: Buffer.from('Photosynthesis converts light energy into chemical energy. Chlorophyll absorbs light.') });
  await expect(page.getByLabel('Attached files')).toContainText('biology.txt');
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Explain this file.');
  await page.getByRole('button', { name: 'Send message' }).click();
  const message = page.getByRole('article', { name: 'Your message' });
  await expect(message).toContainText('biology.txt');
  await expect(message.getByRole('button', { name: 'Add to Library', exact: true })).toBeEnabled({ timeout: 25_000 });
  const before = await page.request.get('http://127.0.0.1:18003/api/v1/documents');
  expect((await before.json()).total).toBe(0);
  await message.getByRole('button', { name: 'Add to Library', exact: true }).click();
  await chooseOption(page.getByLabel('Learning context for biology.txt', { exact: true }), context.context_id);
  await page.getByRole('button', { name: 'Add extracted content', exact: true }).click();
  await expect(message.getByRole('link', { name: 'View in Library · processing status' })).toBeVisible();
  await page.reload();
  await expect(message.getByRole('link', { name: 'View in Library · processing status' })).toBeVisible();
  await message.getByRole('link', { name: 'View in Library · processing status' }).click();
  await expect(page.getByText('Ready to study', { exact: true })).toBeVisible({ timeout: 20_000 });
});
