import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import type { MaterialDocument } from '../src/types/rag';

test('New Chat handoff preserves the first editable draft', async ({ page }) => {
  await workspace(page, false, true);
  await page.goto('/chat/polish-chat');
  await page.getByLabel('Ask Mentra anything').fill('Old draft');
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  const composer = page.getByLabel('Ask Mentra anything');
  await composer.fill('First draft after New Chat');
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page).toHaveURL(/\/$/);
  await expect(composer).toHaveValue('First draft after New Chat');
});

test('guest entry does not download unrelated workspace or Markdown chunks', async ({ page }) => {
  const scripts: string[] = [];
  page.on('request', request => { if (request.resourceType() === 'script') scripts.push(new URL(request.url()).pathname); });
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: { error: { code: 'AUTHENTICATION_FAILED' } } }));
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  expect(scripts.filter(path => /\/(ChatPage|LibraryPage|AssessmentWorkspace|MarkdownContent|OnboardingPage)-/.test(path))).toEqual([]);
});

test.describe('touch controls', () => {
  test.use({ hasTouch: true, isMobile: true });
  test('composer icons keep small glyphs and usable touch targets', async ({ page }) => {
    await workspace(page, false, true);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/chat/polish-chat');
    for (const name of ['Record voice message', 'Send message']) {
      const bounds = await page.getByRole('button', { name, exact: true }).boundingBox();
      expect(bounds!.width).toBeGreaterThanOrEqual(44); expect(bounds!.height).toBeGreaterThanOrEqual(44);
    }
    await page.getByLabel('Upload chat files').setInputFiles({ name: 'touch.txt', mimeType: 'text/plain', buffer: Buffer.from('Touch target fixture') });
    const remove = page.getByRole('button', { name: 'Remove touch.txt' });
    const bounds = await remove.boundingBox(); expect(bounds!.width).toBeGreaterThanOrEqual(44); expect(bounds!.height).toBeGreaterThanOrEqual(44);
    await remove.tap(); await expect(page.getByLabel('Attached files')).toHaveCount(0);
  });
});

test('mobile navigation is modal, restores focus, and retains history after desktop collapse', async ({ page }, info) => {
  await workspace(page, false, true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/library');
  await page.getByRole('button', { name: 'Collapse sidebar' }).click();
  await page.setViewportSize({ width: 390, height: 568 });
  const opener = page.getByRole('button', { name: 'Open navigation menu' });
  await opener.click();
  const navigation = page.getByRole('dialog', { name: 'Main navigation' });
  await expect(navigation).toBeVisible();
  await expect(navigation.getByRole('region', { name: 'Conversation history' })).toBeVisible();
  expect(await page.locator('#workspace-content').evaluate(node => (node as HTMLElement).inert)).toBe(true);
  await navigation.getByRole('button', { name: /Account menu/ }).click();
  await expect(navigation.getByLabel('Account settings')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(navigation.getByLabel('Account settings')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await info.attach('navigation-focus.json', { body: JSON.stringify(await page.evaluate(() => ({ active: document.activeElement?.outerHTML, contentInert: document.getElementById('workspace-content')?.inert, sidebarInert: document.querySelector('aside')?.inert, role: document.querySelector('aside')?.getAttribute('role') }))), contentType: 'application/json' });
  await expect(opener).toBeFocused();
  expect(await page.getByLabel('Main navigation').evaluate(node => (node as HTMLElement).inert)).toBe(true);
  expect(await page.locator('#workspace-content').evaluate(node => (node as HTMLElement).inert)).toBe(false);
  await opener.click();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await page.locator('#workspace-content').evaluate(node => (node as HTMLElement).inert)).toBe(false);
});

test('shared tabs preserve assessment drafts, URL history and keyboard focus', async ({ page }) => {
  await workspace(page, false, true);
  await page.goto('/assessments?tab=create');
  await page.getByLabel('Topic', { exact: true }).fill('A draft to preserve');
  const create = page.getByRole('tab', { name: 'Create new' });
  await create.focus(); await create.press('Home');
  await expect(page.getByRole('tab', { name: 'Assessments', exact: true })).toBeFocused();
  await expect(page).not.toHaveURL(/tab=create/);
  await page.goBack();
  await expect(page.getByLabel('Topic', { exact: true })).toHaveValue('A draft to preserve');
  await create.focus(); await create.press('ArrowLeft'); await page.getByRole('tab', { name: 'Assessments', exact: true }).press('End');
  await expect(create).toBeFocused();
  await expect(page.getByLabel('Topic', { exact: true })).toHaveValue('A draft to preserve');
});

test('refresh keeps understanding rows and coalesces focus and visibility events', async ({ page }) => {
  await workspace(page, false, true);
  let requests = 0;
  await page.route('**/api/v1/learning/understanding*', async route => {
    requests++;
    await new Promise(resolve => setTimeout(resolve, 100));
    await route.fulfill({ json: { items: [{ concept_id: 'forces', name: 'Forces', knowledge_status: 'developing', mastery: .6, estimate_confidence: .5, retention_confidence: .4 }], total: 1, total_concepts: 1, limit: 10, offset: 0 } });
  });
  await page.goto('/progress');
  const row = page.getByRole('row').filter({ hasText: 'Forces' });
  await expect(row).toBeVisible();
  const count = requests;
  await page.evaluate(() => { const now = Date.now.bind(Date); Date.now = () => now() + 31_000; window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')); });
  await expect(row).toBeVisible();
  await expect.poll(() => requests).toBe(count + 1);
  await expect(row).toBeVisible();
});

test('reduced motion and touch-sized targets retain compact desktop geometry', async ({ page }) => {
  await workspace(page, false, true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 800 });
  await page.goto('/library');
  const add = page.getByRole('button', { name: 'Add material', exact: true });
  expect((await add.boundingBox())!.height).toBeLessThanOrEqual(40);
  await add.click();
  await expect(page.getByRole('heading', { name: 'Add material' })).toBeVisible();
  expect(await page.locator('main').evaluate(node => getComputedStyle(node).transitionDuration)).toBe('1e-05s');
});

test('material refresh protects dirty details and source dialogs remain open until dismissed', async ({ page }) => {
  await workspace(page, false, true);
  let document: MaterialDocument = { id: 'material-1', title: 'Saved title', filename: 'notes.txt', context_ids: ['context-1'], archived: false, revision: 1, active_generation_id: 'generation-1', version_count: 1, versions: [{ id: 'version-1', filename: 'notes.txt', media_type: 'text/plain', size_bytes: 100, created_at: '2026-10-14T00:00:00Z' }], generations: [{ id: 'generation-1', version_id: 'version-1', state: 'READY', warnings: [], chunk_count: 0 }], jobs: [] };
  await page.route('**/api/v1/documents/material-1', route => route.fulfill({ json: document }));
  await page.goto('/library/material-1');
  await page.getByLabel('Title', { exact: true }).fill('Unsent draft');
  document = { ...document, revision: 2, title: 'Changed elsewhere' };
  await page.evaluate(() => { const now = Date.now.bind(Date); Date.now = () => now() + 31_000; window.dispatchEvent(new Event('focus')); });
  await expect(page.getByRole('alert')).toContainText('Your draft is preserved');
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue('Unsent draft');
  await expect(page.getByRole('button', { name: 'Save material details' })).toBeDisabled();
  await page.getByRole('button', { name: 'Reload saved details' }).click();
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue('Changed elsewhere');
  const source = page.getByRole('button', { name: 'Open source version' });
  await source.click();
  const dialog = page.getByRole('dialog', { name: 'Source: Changed elsewhere' });
  await expect(dialog.getByText('No extracted passages are available', { exact: false })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(source).toBeFocused();
});
