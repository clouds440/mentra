import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

async function register(page: Page) {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`rag_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('a unique RAG test passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await expect(page).toHaveURL(/\/$/);
}

test('Library upload, refresh, grounded chat, citation, replacement and deletion', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`rag_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('a unique RAG test passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await page.goto('/library');
  await expect(page.getByRole('heading', { name: 'Library', exact: true })).toBeVisible();
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'decorators.txt', mimeType: 'text/plain', buffer: Buffer.from('Python decorators wrap functions. They add reusable behavior to a function.') });
  await page.getByLabel('Material title', { exact: true }).fill('Decorator Notes');
  await page.getByLabel('New context name', { exact: true }).fill('Python');
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Upload accepted');
  await page.reload();
  await expect(page.getByRole('link', { name: 'Study in chat', exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('link', { name: 'Study in chat', exact: true }).click();
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Explain decorators from my notes.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('button', { name: 'Open cited source Decorator Notes' })).toBeVisible();
  await page.getByRole('button', { name: 'Open cited source Decorator Notes' }).click();
  await expect(page.getByRole('dialog', { name: 'Source: Decorator Notes' })).toBeVisible();
  await expect(page.getByRole('dialog').getByText('Python decorators wrap functions.', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('dialog').locator('section')).toHaveCount(1);
  const sourceBounds = await page.getByRole('dialog').boundingBox();
  expect(Math.abs(sourceBounds!.y + sourceBounds!.height / 2 - page.viewportSize()!.height / 2)).toBeLessThan(2);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download original' }).click(); await download;
  await page.getByRole('button', { name: 'Close source' }).click();
  await page.goto('/library');
  await page.getByRole('link', { name: 'Decorator Notes', exact: true }).click();
  await expect(page.getByText('Ready to study', { exact: true })).toBeVisible();
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'decorators-v2.txt', mimeType: 'text/plain', buffer: Buffer.from('Python decorators now have revised source examples and reusable wrappers.') });
  await page.getByRole('button', { name: 'Submit replacement', exact: true }).click();
  await expect(page.getByText(/decorators-v2.txt.*Latest upload/)).toBeVisible();
  await expect(page.getByText('Ready to study', { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Archive material', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Unarchive material', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Unarchive material', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Archive material', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reindex material', exact: true }).click();
  await expect(page.getByText('Ready to study', { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Delete material', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page).toHaveURL(/\/library\?deleted=1$/);
  await expect(page.getByRole('link', { name: 'Decorator Notes', exact: true })).toHaveCount(0);
});

for (const theme of ['light', 'dark'] as const) {
  test(`RAG Library and keyboard citations fit mobile in ${theme} theme`, async ({ page }, testInfo) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await register(page);
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto('/library');
    await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Python decorators wrap functions and add reusable behavior.') });
    await page.getByLabel('Material title', { exact: true }).fill('Mobile Notes');
    await page.getByLabel('New context name', { exact: true }).fill('Python');
    await page.getByRole('button', { name: 'Upload material', exact: true }).click();
    await expect(page.getByRole('link', { name: 'Study in chat', exact: true })).toBeVisible({ timeout: 20_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`library-${theme}-320.png`), fullPage: true });
    await page.getByRole('link', { name: 'Study in chat', exact: true }).click();
    await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Explain decorators');
    await page.getByRole('button', { name: 'Send message' }).click();
    const citation = page.getByRole('button', { name: 'Open cited source Mobile Notes' });
    await expect(citation).toBeVisible(); await citation.focus(); await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    expect(await page.getByRole('dialog').evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`citation-${theme}-320.png`), fullPage: true });
    await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(citation).toBeFocused();
  });
}

test('a second signed-in learner cannot fetch or ground chat with another learner’s material', async ({ page, browser }) => {
  await register(page);
  const headers = { Origin: 'http://127.0.0.1:15173' };
  const created = await page.request.post('http://127.0.0.1:18003/api/v1/learning-contexts', { headers, data: { name: 'Private course', activate: true } });
  expect(created.ok()).toBe(true);
  const context = await created.json();
  const upload = await page.request.post('http://127.0.0.1:18003/api/v1/documents', { headers, multipart: {
    context_ids: JSON.stringify([context.context_id]), idempotency_key: randomUUID(), title: 'Private notes',
    file: { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Private decorators wrap functions.') },
  } });
  expect(upload.status()).toBe(202); const material = await upload.json();
  const second = await browser.newContext();
  try {
    const other = await second.newPage(); await register(other);
    expect((await second.request.get(`http://127.0.0.1:18003/api/v1/documents/${material.document_id}`)).status()).toBe(404);
    expect((await second.request.post('http://127.0.0.1:18003/api/v1/chat', { headers, data: {
      messages: [{ role: 'user', content: 'Read these notes' }], retrieval: { mode: 'SOURCE_SPECIFIC', document_ids: [material.document_id] },
    } })).status()).toBe(404);
    const list = await second.request.get('http://127.0.0.1:18003/api/v1/documents');
    expect((await list.json()).items).toEqual([]);
  } finally { await second.close(); }
});

test('removed source selections stay explicit and switching to automatic clears archive consent', async ({ page }) => {
  await register(page);
  await page.goto('/?document=removed-material');
  await page.getByText('Using selected material', { exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Some selected material is unavailable');
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Use my selected notes');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('alert')).toContainText('Choose study sources before sending');
  await expect(page.getByRole('article', { name: 'Mentra response' })).toHaveCount(0);
  await page.getByLabel('Allow explicitly selected archived material').check();
  await page.getByLabel('Study sources', { exact: true }).selectOption('STANDARD');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('article', { name: 'Mentra response' })).toContainText('No supporting Library material was found');
});
