import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

test('skill modal scrolls its body while keeping Close visible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 700 }); await workspace(page);
  const topic = { id: 'topic-test', name: 'Differentiation', scope: 'Practice rules', revision: 1, subskill_count: 10, checked_count: 0 };
  await page.route('**/api/v1/learning/topics**', route => route.fulfill({ json: route.request().url().includes('/subskills') ? {
    topic, items: Array.from({ length: 10 }, (_, index) => ({ concept_id: `skill-${index}`, name: `Rule ${index}`, ability: 'A detailed explanation. '.repeat(8), knowledge_status: 'insufficient_evidence' })), total: 10, limit: 10, offset: 0,
  } : { items: [topic], total: 1, ungrouped_count: 0, limit: 10, offset: 0 } }));
  await page.goto('/progress'); await page.getByRole('button', { name: 'Explore Differentiation', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Topic subskills' });
  const close = dialog.getByRole('button', { name: 'Close subskills' });
  await expect(dialog.getByText('Rule 0', { exact: true })).toBeVisible();
  const before = await close.boundingBox();
  const body = dialog.locator('[data-skill-scroll]');
  expect(await body.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
  await body.evaluate(node => { node.scrollTop = node.scrollHeight; });
  expect(await close.boundingBox()).toEqual(before); await expect(close).toBeVisible();
  await close.click(); await expect(dialog).not.toBeVisible();
});
