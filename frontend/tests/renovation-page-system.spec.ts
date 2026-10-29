import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { chooseOption } from './select-helpers';

const routes = ['/library', '/library/new', '/library/material-1', '/progress', '/progress?tab=events', '/assessments', '/assessments?tab=create', '/assessments?tab=mistakes', '/settings', '/settings?tab=memories', '/settings?tab=notifications'];
for (const width of [360, 768, 1440]) test(`standard page frames and tabs stay within ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await workspace(page);
  await page.route('**/api/v1/documents/material-1', route => route.fulfill({ json: { id: 'material-1', title: 'Motion and forces', filename: 'Physics notes.pdf', context_ids: [], archived: false, revision: 1, active_generation_id: null, versions: [], version_count: 0, generations: [], jobs: [] } }));
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  for (const route of routes) {
    await page.goto(route);
    await expect(page.locator('.workspace-page')).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    await expect(page.locator('.workspace-page .workspace-header')).toBeVisible();
    if (route.startsWith('/assessments')) await expect(page.getByRole('button', { name: 'New assessment', exact: true })).toHaveCount(0);
    await page.waitForTimeout(100);
    if (width === 1440 && ['/library', '/settings', '/progress?tab=events'].includes(route)) await page.screenshot({ path: `test-results/page-system-${route === '/library' ? 'library' : route === '/settings' ? 'settings' : 'events'}.png` });
    expect(await page.locator('.workspace-page').evaluate(node => node.scrollWidth <= node.clientWidth + 1), route).toBe(true);
  }
  expect(errors).toEqual([]);
});

test('event history and narrow dropdowns retain their content', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 850 }); await workspace(page);
  let requested = '';
  const event = { id: 'saved-event', revision: 2, title: 'Completed study session', status: 'completed', kind: 'study', timezone: 'UTC', local_date: '2020-01-01', bucket: 'completed', reminder_state: 'skipped' };
  await page.route('**/api/v1/events/page?*', route => {
    requested = route.request().url();
    return route.fulfill({ json: { items: [event], next_cursor: null, detail: null, proposals: [], proposals_error: false } });
  });
  await page.goto('/progress?tab=events');
  await expect(page.getByText('Completed study session', { exact: true })).toBeVisible();
  expect(requested).toContain('status=all'); expect(requested).toContain('all_dates=true');
  const selector = page.getByRole('combobox', { name: 'Event date range' });
  await selector.click();
  const menu = page.getByRole('listbox'); await expect(menu).toBeVisible();
  expect(await menu.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  for (const option of await menu.getByRole('option').all()) {
    const bounds = await option.locator('span').first().boundingBox(); const frame = await menu.boundingBox();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(frame!.x + frame!.width);
  }
  await page.keyboard.press('Escape');
  await chooseOption(page.getByRole('combobox', { name: 'Event status' }), 'completed');
  await expect(page.getByText('Completed study session', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Hide history', exact: true })).toBeVisible();
  await expect(page.getByText('No past decisions yet.')).toBeVisible();
});

test('profile editing uses a modal without moving the page header', async ({ page }) => {
  await workspace(page); await page.goto('/settings');
  const header = page.locator('.workspace-header'); const initial = await header.boundingBox();
  await page.getByRole('button', { name: 'Edit profile', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Edit learning profile' })).toBeVisible();
  expect(await header.boundingBox()).toEqual(initial);
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Edit profile', exact: true })).toBeFocused();
});

test('dark workspace uses the same frames with populated library cards', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('mentra-theme', 'dark'));
  await page.setViewportSize({ width: 1280, height: 900 });
  await workspace(page, false, true);
  for (const route of ['/library', '/assessments?tab=mistakes', '/settings?tab=notifications', '/progress?tab=events']) {
    await page.goto(route); await expect(page.locator('.workspace-page')).toBeVisible();
    expect(await page.locator('.workspace-page').evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  }
});
test('dismissed suggestions remain visible after reload without per-card requests', async ({ page }) => {
  await workspace(page);
  let detailRequests = 0;
  await page.route('**/api/v1/event-proposals/dismissed-1', route => { detailRequests++; return route.fulfill({ json: {} }); });
  await page.route('**/api/v1/event-proposals?*', route => route.fulfill({ json: [{ id: 'dismissed-1', revision: 2, state: 'dismissed', action: 'create', candidate: { title: 'Earlier event suggestion', timezone: 'UTC', local_date: '2020-01-01' }, uncertainty: 'Suggested from your conversation', quote: 'A useful historical source' }] }));
  await page.goto('/progress?tab=events');
  await expect(page.getByRole('heading', { name: 'Earlier event suggestion', exact: true })).toBeVisible();
  await expect(page.getByText('Proposal dismissed.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Proposal dismissed.', { exact: true })).toBeVisible();
  expect(detailRequests).toBe(0);
});
