import { expect, test } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { richChat } from './renovation-rich-fixtures';

for (const width of [390, 1280]) test(`side panel close control stays fixed while a long source scrolls at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await workspace(page, false, true);
  await page.route('**/api/v1/documents/material-1', route => route.fulfill({ json: {
    id: 'material-1', title: 'Long learning source', filename: 'notes.txt', context_ids: ['context-1'], archived: false, revision: 1,
    active_generation_id: 'generation-1', version_count: 1, jobs: [], generations: [{ id: 'generation-1', version_id: 'version-1', state: 'READY', warnings: [], chunk_count: 5 }],
    versions: [{ id: 'version-1', filename: 'notes.txt', media_type: 'text/plain', size_bytes: 10000, generation_id: 'generation-1', extraction_state: 'ready', created_at: '2026-11-03T00:00:00Z' }],
  } }));
  await page.route('**/api/v1/documents/material-1/versions/version-1/chunks?**', route => route.fulfill({ json: Array.from({ length: 5 }, (_, index) => ({
    id: `chunk-${index}`, content: `Section ${index + 1}\n` + 'A clear explanation with examples and supporting details. '.repeat(80), heading_path: [], spans: [],
  })) }));
  await page.goto('/library/material-1');
  const opener = page.getByRole('button', { name: 'Open source version', exact: true });
  await opener.click();
  const dialog = page.getByRole('tabpanel', { name: 'notes.txt' });
  const close = page.getByRole('button', { name: 'Hide side panel', exact: true });
  await expect(dialog.getByText('Section 5', { exact: false })).toBeVisible();
  await expect(close).toHaveCount(1);
  const before = await close.boundingBox();
  await dialog.locator('.source-reader').evaluate(node => { node.scrollTop = node.scrollHeight; });
  await dialog.evaluate(node => { node.scrollTop = node.scrollHeight; });
  await expect(close).toBeInViewport();
  expect(await close.boundingBox()).toEqual(before);
  expect(await page.locator('#workspace-side-panel').evaluate(node => node.scrollTop)).toBe(0);
  await close.click();
  await expect(dialog).toHaveCount(0);
  await expect(width < 1200 ? opener : page.getByRole('button', { name: 'Open side panel', exact: true })).toBeFocused();
});

test('chat reference opens in the side panel and its fullscreen diagram closes independently', async ({ page }) => {
  const fixture = await richChat(page, 'From our earlier discussion [[H1]].');
  Object.assign(fixture.items[1], { history_references: [{ token: 'H1', conversation_id: 'older-chat', title: 'Earlier notes', sequence: 1 }] });
  await page.route('**/api/v1/memories/history/older-chat?**', route => route.fulfill({ json: {
    title: 'Earlier notes', conversation_id: 'older-chat', messages: [{ id: 'old-message', role: 'assistant', created_at: '2026-11-03T00:00:00Z',
      content: 'An earlier explanation with useful details. '.repeat(160) + '\n\n```mermaid\nflowchart LR\n A[Read] --> B[Practice]\n```' }],
  } }));
  await page.goto('/chat/polish-chat');
  const opener = page.getByRole('button', { name: 'Open history reference H1' });
  await opener.click();
  const parent = page.getByRole('tabpanel', { name: 'Earlier notes' });
  const close = page.getByRole('button', { name: 'Hide side panel', exact: true });
  await expect(close).toBeVisible();
  await expect.poll(async () => Math.round((await page.locator('#workspace-side-panel').boundingBox())!.width)).toBe(410);
  const bounds = await close.boundingBox();
  await parent.locator('[data-visual-kind="diagram"]').scrollIntoViewIfNeeded();
  await expect(close).toBeInViewport();
  expect(await close.boundingBox()).toEqual(bounds);
  await parent.getByRole('button', { name: 'Expand', exact: true }).click();
  const nested = page.getByRole('dialog', { name: 'Expanded diagram' });
  await expect(nested).toBeVisible();
  await nested.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(nested).toHaveCount(0);
  await expect(parent).toBeVisible();
  await close.click();
  await expect(parent).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Open side panel', exact: true })).toBeFocused();
});
