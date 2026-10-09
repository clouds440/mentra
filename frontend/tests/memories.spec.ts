import { chooseOption } from './select-helpers';
import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

async function register(page: Page) {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`memory_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('a persistent memory test passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
}
async function send(page: Page, content: string) {
  const response = page.waitForResponse(value => value.url().endsWith('/conversations/turns'));
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill(content);
  await page.getByRole('button', { name: 'Send message' }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole('article', { name: 'Mentra response' }).last()).toBeVisible();
}

test('Settings drawer, tabs, manual CRUD, evidence and draft retention', async ({ page }, info) => {
  await register(page);
  let prefetches = 0;
  page.on('request', request => { if (request.url().includes('/api/v1/memories')) prefetches++; });
  await page.getByRole('button', { name: /Account menu for/ }).click();
  await page.getByRole('link', { name: 'Memories', exact: true }).click();
  await expect(page).toHaveURL(/settings\?tab=memories/);
  await expect(page.getByRole('tab', { name: 'Memories' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('A fresh start')).toBeVisible();
  await page.getByRole('button', { name: 'Add memory', exact: true }).click();
  await page.getByRole('textbox', { name: 'Memory', exact: true }).fill('I prefer beautifully highlighted TypeScript examples.');
  await page.getByRole('tab', { name: 'Profile & preferences' }).click();
  await page.getByRole('tab', { name: 'Memories' }).click();
  await expect(page.getByRole('textbox', { name: 'Memory', exact: true })).toHaveValue('I prefer beautifully highlighted TypeScript examples.');
  await page.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByText('Memory saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Evidence', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Memory evidence' })).toContainText('Manual entry');
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByRole('textbox', { name: 'Memory', exact: true }).fill('I prefer Python examples.');
  await page.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByRole('list').filter({ hasText: 'I prefer Python examples.' })).toBeVisible();
  await page.getByRole('button', { name: 'Pin', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Unpin', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Unpin', exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath('memories-settings.png'), animations: 'disabled' });
  await page.getByRole('tab', { name: 'Memories' }).focus();
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByRole('tab', { name: 'Profile & preferences' })).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Memories' })).toBeFocused();
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.getByText('A fresh start')).toBeVisible();
  expect(prefetches).toBeGreaterThan(0);
});

test('actual memory/history tool calls, references, chat deletion retention and inference confirmation', async ({ page }) => {
  await register(page);
  await send(page, 'Remember that I prefer mermaid diagrams.');
  const sourceChat = page.url();
  await expect(page.getByRole('article', { name: 'Mentra response' })).toContainText('Memory saved.');
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  await expect(page).toHaveURL(/\/$/);
  await send(page, 'Recall memories about diagrams');
  await page.getByRole('button', { name: 'Open memory reference M1' }).click();
  await expect(page.getByRole('dialog')).toContainText('Remember that I prefer mermaid diagrams.');
  await page.getByRole('button', { name: 'Close reference' }).click();
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  await expect(page).toHaveURL(/\/$/);
  await send(page, 'Find past chats about mermaid');
  await page.getByRole('button', { name: 'Open history reference H1' }).click();
  await expect(page.getByRole('dialog')).toContainText('Remember that I prefer mermaid diagrams.');
  await page.getByRole('button', { name: 'Close reference' }).click();
  await page.goto(sourceChat);
  await page.getByRole('button', { name: 'Delete Remember that I prefer mermaid diagrams.', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await page.goto('/settings?tab=memories');
  await page.getByRole('button', { name: 'Evidence', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Memory evidence' })).toContainText('Source chat deleted');
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  await send(page, 'Maybe I prefer visual puzzles.');
  await expect(page.getByRole('article', { name: 'Mentra response' }).last()).toContainText('pending');
  await page.goto('/settings?tab=memories');
  await chooseOption(page.getByLabel('Memory status'), 'pending');
  await expect(page.getByRole('region', { name: 'Memories', exact: true }).getByText('Maybe I prefer visual puzzles.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm current', exact: true }).click();
  await expect(page.getByText('No matching memories')).toBeVisible();
  await chooseOption(page.getByLabel('Memory status'), 'active');
  await expect(page.getByRole('region', { name: 'Memories', exact: true }).getByText('Maybe I prefer visual puzzles.', { exact: true })).toBeVisible();
});

test('memory disabled and mobile settings layout', async ({ page }, info) => {
  await register(page);
  await page.goto('/settings?tab=memories');
  const checkbox = page.getByRole('switch', { name: 'Let Mentra save useful memories', exact: true });
  await checkbox.uncheck();
  await expect(checkbox).not.toBeChecked();
  await page.reload();
  await expect(checkbox).not.toBeChecked();
  await checkbox.focus();
  await page.keyboard.press('Space');
  await expect(checkbox).toBeChecked();
  await expect(checkbox).toBeEnabled();
  await checkbox.focus();
  await page.keyboard.press('Space');
  await expect(checkbox).not.toBeChecked();
  await expect(checkbox).toBeEnabled();
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  await send(page, 'Remember that I like concise answers.');
  await expect(page.getByRole('article', { name: 'Mentra response' })).toContainText('rejected');
  await page.goto('/settings?tab=memories');
  await expect(page.getByText('A fresh start')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('tab', { name: 'Memories' })).toBeVisible();
  const add = page.getByRole('button', { name: 'Add memory', exact: true });
  expect(await add.evaluate(element => getComputedStyle(element).whiteSpace)).toBe('nowrap');
  expect((await add.boundingBox())!.height).toBeLessThanOrEqual(40);
  await page.screenshot({ path: info.outputPath('memories-mobile.png'), animations: 'disabled' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('stale preference and delete revisions recover without discarding the current statement', async ({ page }) => {
  await register(page);
  await page.goto('/settings?tab=memories');
  const toggle = page.getByRole('switch', { name: 'Let Mentra save useful memories', exact: true });
  await expect(toggle).toBeEnabled();
  const api = 'http://127.0.0.1:18003/api/v1/memories';
  const headers = { Origin: 'http://127.0.0.1:15173' };
  const prefs = await (await page.request.get(`${api}/preferences`)).json();
  expect((await page.request.patch(`${api}/preferences`, { headers, data: { automatic_memory: false, expected_revision: prefs.revision } })).ok()).toBe(true);
  const conflictResponse = page.waitForResponse(response => response.url().endsWith('/memories/preferences') && response.request().method() === 'PATCH');
  await toggle.uncheck();
  expect((await conflictResponse).status()).toBe(409);
  await expect(page.getByText('Another session changed your memory settings or records.', { exact: false })).toBeVisible();
  await expect(toggle).not.toBeChecked();
  await expect(toggle).toBeEnabled();
  await toggle.check();
  await expect(toggle).toBeEnabled();
  expect((await (await page.request.get(`${api}/preferences`)).json()).automatic_memory).toBe(true);
  await page.getByRole('button', { name: 'Add memory', exact: true }).click();
  await page.getByRole('textbox', { name: 'Memory', exact: true }).fill('Original statement before concurrent edit.');
  await page.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByText('Memory saved.', { exact: true })).toBeVisible();
  const list = await (await page.request.get(api)).json();
  const memory = list.items[0];
  expect((await page.request.patch(`${api}/${memory.id}`, { headers, data: { content: 'Updated statement that must be reviewed.', expected_revision: memory.revision } })).ok()).toBe(true);
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.getByRole('alertdialog')).toContainText('Updated statement that must be reviewed.');
  await expect(page.getByRole('button', { name: 'Confirm deletion', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.getByText('A fresh start')).toBeVisible();
});

test('a delayed pagination response cannot leak rows into a changed status filter', async ({ page }) => {
  await register(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let requested!: () => void;
  const started = new Promise<void>(resolve => { requested = resolve; });
  const row = { id: randomUUID(), content: 'Saved row from the old filter.', category: 'fact', status: 'active', origin: 'manual', revision: 1, conflicts: [], pinned: false, stale: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), confirmed_at: null, expires_at: null };
  await page.route('**/api/v1/memories?*', async route => {
    const url = new URL(route.request().url());
    if (url.searchParams.has('cursor')) { requested(); await gate; }
    const pending = url.searchParams.get('status') === 'pending';
    await route.fulfill({ json: { items: pending ? [] : [row], next_cursor: pending ? null : 'next-page' } }).catch(() => undefined);
  });
  await page.goto('/settings?tab=memories');
  await expect(page.getByText(row.content, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Load more memories', exact: true }).click();
  await started;
  await chooseOption(page.getByLabel('Memory status'), 'pending');
  await expect(page.getByText('No matching memories')).toBeVisible();
  release();
  await expect(page.getByText(row.content, { exact: true })).toHaveCount(0);
  await chooseOption(page.getByLabel('Memory status'), 'active');
  await expect(page.getByText(row.content, { exact: true })).toBeVisible();
});

test('capacity rejection preserves the actionable error and the unsaved draft', async ({ page }) => {
  await register(page);
  await page.goto('/settings?tab=memories');
  await expect(page.getByText('A fresh start')).toBeVisible();
  await page.route('**/api/v1/memories', async route => {
    if (route.request().method() === 'POST') await route.fulfill({ status: 409, json: { error: { code: 'MEMORY_CAPACITY', message: 'Memory capacity reached (1000). Delete unused memories first.' } } });
    else await route.continue();
  });
  await page.getByRole('button', { name: 'Add memory', exact: true }).click();
  const editor = page.getByRole('textbox', { name: 'Memory', exact: true });
  await editor.fill('My draft must survive a capacity rejection.');
  await page.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save memory', exact: true })).toBeEnabled();
  await expect(page.getByRole('alert')).toContainText('Delete unused memories first.');
  await expect(editor).toHaveValue('My draft must survive a capacity rejection.');
  await expect(page.getByText('Another session changed', { exact: false })).toHaveCount(0);
});

test('conflicting memories require review and exclude the predecessor from recall', async ({ page }) => {
  await register(page);
  await send(page, 'Remember my favorite color is violet.');
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  await expect(page).toHaveURL(/\/$/);
  await send(page, 'Remember my favorite color is amber.');
  await expect(page.getByRole('article', { name: 'Mentra response' }).last()).toContainText('conflict');
  await page.goto('/settings?tab=memories');
  await chooseOption(page.getByLabel('Memory status'), 'conflict');
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByRole('textbox', { name: 'Memory', exact: true }).fill('My favorite color is amber, especially for diagrams.');
  await page.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByRole('alertdialog', { name: 'Resolve memory conflict' })).toContainText('Remember my favorite color is violet.');
  await expect(page.getByRole('alertdialog', { name: 'Resolve memory conflict' })).toContainText('My favorite color is amber, especially for diagrams.');
  await page.getByRole('button', { name: 'Keep this statement', exact: true }).click();
  await expect(page.getByRole('alertdialog', { name: 'Resolve memory conflict' })).toHaveCount(0);
  await chooseOption(page.getByLabel('Memory status'), 'active');
  const memories = page.getByRole('region', { name: 'Memories', exact: true });
  await expect(memories.getByText('My favorite color is amber, especially for diagrams.', { exact: true })).toBeVisible();
  await expect(memories.getByText('Remember my favorite color is violet.', { exact: true })).toHaveCount(0);
});

test('memory pages load only on demand, reconcile another tab and retain profile drafts', async ({ page, context }) => {
  let calls = 0;
  page.on('request', request => { if (request.url().includes('/api/v1/memories')) calls++; });
  await register(page);
  await page.goto('/settings');
  await page.getByRole('button', { name: 'Edit profile', exact: true }).click();
  await page.getByLabel('Field or area of study', { exact: true }).fill('Draft physics');
  expect(calls).toBe(0);
  await page.getByRole('tab', { name: 'Memories' }).click();
  await expect(page.getByText('A fresh start')).toBeVisible();
  await page.getByRole('tab', { name: 'Profile & preferences' }).click();
  await expect(page.getByLabel('Field or area of study', { exact: true })).toHaveValue('Draft physics');
  await page.getByRole('tab', { name: 'Memories' }).click();
  const peer = await context.newPage();
  await peer.goto('/settings?tab=memories');
  await peer.getByRole('button', { name: 'Add memory', exact: true }).click();
  await peer.getByRole('textbox', { name: 'Memory', exact: true }).fill('Cross-tab saved preference.');
  await peer.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByText('Cross-tab saved preference.', { exact: true })).toBeVisible();
  await peer.close();
});
