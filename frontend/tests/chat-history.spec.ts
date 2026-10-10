import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

async function register(page: Page) {
  const username = `history_${randomUUID().slice(0, 8)}`;
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill('a persistent history passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await expect(page).toHaveURL(/\/$/);
  return username;
}
async function send(page: Page, content: string) {
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill(content);
  const response = page.waitForResponse(r => r.url().endsWith('/conversations/turns'));
  await page.getByRole('button', { name: 'Send message' }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole('article', { name: 'Mentra response' }).last()).toBeVisible();
  // Streaming can render an assistant article before the durable turn finishes.
  // Cache-navigation assertions must not count the preceding turn's final poll.
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeEnabled();
}

test('durable history, incremental requests, cached navigation, rename and deletion', async ({ page }, testInfo) => {
  const bodies: Record<string, unknown>[] = [];
  page.on('request', request => { if (request.url().endsWith('/conversations/turns')) bodies.push(request.postDataJSON()); });
  await register(page);
  await send(page, 'First saved question');
  const firstURL = page.url();
  await expect(page.getByRole('link', { name: 'First saved question', exact: true })).toBeVisible();
  await send(page, 'Second saved question');
  expect(bodies).toHaveLength(2);
  expect(bodies[1].content).toBe('Second saved question');
  expect(bodies[1]).not.toHaveProperty('messages');
  expect(JSON.stringify(bodies[1])).not.toContain('First saved question');
  await page.reload();
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(2);
  await expect(page.getByRole('article', { name: 'Mentra response' })).toHaveCount(2);
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  await send(page, 'Separate saved conversation');
  await page.getByRole('link', { name: 'First saved question', exact: true }).click();
  await expect(page).toHaveURL(firstURL);
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(2);
  let loads = 0;
  page.on('request', request => { if (/\/conversations\/[^/]+\/status/.test(request.url())) loads++; });
  await page.getByRole('link', { name: 'Library', exact: true }).click();
  await page.getByRole('link', { name: 'First saved question', exact: true }).click();
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(2);
  expect(loads).toBe(0);
  await page.getByRole('button', { name: 'Rename First saved question', exact: true }).click();
  await page.getByLabel('Conversation title', { exact: true }).fill('Renamed persistent chat');
  await page.getByRole('button', { name: 'Save conversation title' }).click();
  await expect(page.getByRole('link', { name: 'Renamed persistent chat', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('persistent-chat.png'), animations: 'disabled' });
  await page.goto('/settings');
  await expect(page.getByText(/Google Drive|Optional backup/)).toHaveCount(0);
  const cached = await page.evaluate(async () => {
    const databases = await indexedDB.databases();
    return databases.filter(db => db.name?.startsWith('mentra-chat-v1-')).length;
  });
  expect(cached).toBe(1);
  await page.getByRole('link', { name: 'Renamed persistent chat', exact: true }).click();
  await page.getByRole('button', { name: 'Delete Renamed persistent chat', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('link', { name: 'Renamed persistent chat', exact: true })).toHaveCount(0);
  await page.goto(firstURL);
  await expect(page.getByRole('alert').first()).toContainText('Conversation not found');
});

test('lost completion response recovers saved messages without another generation', async ({ page }) => {
  await register(page);
  await page.route('**/conversations/turns', async route => { await route.fetch(); await route.abort('failed'); });
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Save despite lost response');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('article', { name: 'Mentra response' })).toHaveCount(1);
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole('article', { name: 'Mentra response' })).toHaveCount(1);
});

test('cross-tab synchronization and logout isolate persistent caches', async ({ page, context }) => {
  const username = await register(page);
  await send(page, 'Shared tab conversation');
  const other = await context.newPage();
  await other.goto('/');
  await expect(other.getByRole('link', { name: 'Shared tab conversation', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Rename Shared tab conversation', exact: true }).click();
  await page.getByLabel('Conversation title', { exact: true }).fill('Updated in another tab');
  await page.getByRole('button', { name: 'Save conversation title' }).click();
  await expect(other.getByRole('link', { name: 'Updated in another tab', exact: true })).toBeVisible();
  await page.getByRole('button', { name: /Account menu/ }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(other).toHaveURL(/\/login$/);
  await expect.poll(async () => page.evaluate(async () => (await indexedDB.databases()).filter(db => db.name?.startsWith('mentra-chat-v1-')).length)).toBe(0);
  await register(page);
  await expect(page.getByRole('link', { name: 'Updated in another tab', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: /Account menu/ }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill('a persistent history passphrase');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Updated in another tab', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Updated in another tab', exact: true }).click();
  await expect(page.getByRole('article', { name: 'Your message' })).toContainText('Shared tab conversation');
});

test('unaccepted send can be retried and blocked IndexedDB remains usable', async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(window, 'indexedDB', { get() { throw new Error('Storage blocked'); } }); });
  await register(page);
  let rejected = false;
  await page.route('**/conversations/turns', async route => {
    if (!rejected) { rejected = true; await route.abort('failed'); }
    else await route.continue();
  });
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Retry an unaccepted question');
  await page.getByRole('button', { name: 'Send message' }).click();
  await page.getByRole('button', { name: 'Retry sending', exact: true }).click();
  await expect(page.getByRole('article', { name: 'Mentra response' })).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole('article', { name: 'Your message' })).toHaveCount(1);
  await expect(page.getByRole('article', { name: 'Your message' })).toContainText('Retry an unaccepted question');
});

test('long history uses bounded pages and maintains chronological ordering', async ({ page }) => {
  await register(page);
  await send(page, 'Long history start');
  const id = page.url().split('/').at(-1)!;
  for (let i = 0; i < 23; i++) {
    const current = await page.request.get(`http://127.0.0.1:18003/api/v1/conversations/${id}/status`);
    const revision = (await current.json()).conversation.revision;
    const result = await page.request.post('http://127.0.0.1:18003/api/v1/conversations/turns', {
      headers: { Origin: 'http://127.0.0.1:15173' },
      data: { conversation_id: id, client_turn_id: randomUUID(), expected_revision: revision, content: `History question ${i}`, retrieval: { mode: 'STANDARD' } },
    });
    expect(result.status()).toBe(200);
  }
  await page.reload();
  await expect(page.getByRole('article')).toHaveCount(40);
  await page.getByRole('button', { name: 'Load earlier messages', exact: true }).click();
  await expect(page.getByRole('article')).toHaveCount(48);
  await expect(page.getByRole('article', { name: 'Your message' }).first()).toContainText('Long history start');
  await expect(page.getByRole('article', { name: 'Your message' }).last()).toContainText('History question 22');
});

test('render window remains bounded and sending from older history returns to latest', async ({ page }) => {
  test.setTimeout(90_000);
  await register(page); await send(page, 'Window history start');
  const id = page.url().split('/').at(-1)!;
  let revision = 3;
  for (let i = 0; i < 105; i++) {
    const response = await page.request.post('http://127.0.0.1:18003/api/v1/conversations/turns', {
      headers: { Origin: 'http://127.0.0.1:15173' },
      data: { conversation_id: id, client_turn_id: randomUUID(), expected_revision: revision, content: `Window question ${i}`, retrieval: { mode: 'STANDARD' } },
    });
    expect(response.status()).toBe(200); revision = (await response.json()).conversation.revision;
  }
  await page.reload(); await expect(page.getByRole('article')).toHaveCount(40);
  for (const expected of [80, 120, 160, 200, 200]) {
    const response = page.waitForResponse(r => r.url().includes('/messages?before='));
    await page.getByRole('button', { name: 'Load earlier messages', exact: true }).click(); await response;
    await expect(page.getByRole('article')).toHaveCount(expected);
  }
  await expect(page.getByRole('button', { name: 'Back to latest messages' })).toBeVisible();
  await expect(page.getByRole('article', { name: 'Your message' }).first()).toContainText('Window history start');
  await send(page, 'Send after browsing older history');
  await expect(page.getByRole('article', { name: 'Your message' }).last()).toContainText('Send after browsing older history');
  await expect(page.getByRole('article', { name: 'Your message' }).nth(-2)).toContainText('Window question 104');
  await expect(page.getByRole('article')).toHaveCount(42);
});

test('a delayed completion cannot resurrect a chat deleted in another tab', async ({ page, context }) => {
  await register(page); await send(page, 'Deletion race conversation');
  const url = page.url();
  let release!: () => void;
  const wait = new Promise<void>(resolve => { release = resolve; });
  let completed!: () => void;
  const ready = new Promise<void>(resolve => { completed = resolve; });
  await page.route('**/conversations/turns', async route => {
    const response = await route.fetch(); completed(); await wait;
    await route.fulfill({ response });
  });
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Delayed completion question');
  await page.getByRole('button', { name: 'Send message' }).click(); await ready;
  const other = await context.newPage(); await other.goto(url);
  await expect(other.getByRole('article', { name: 'Mentra response' })).toHaveCount(2);
  await expect(other.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeEnabled();
  await other.getByRole('button', { name: 'Delete Deletion race conversation', exact: true }).click();
  await other.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Deletion race conversation', exact: true })).toHaveCount(0);
  release();
  await expect(page.getByRole('article')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('alert').first()).toContainText('Conversation not found');
  await expect(page.getByRole('article')).toHaveCount(0);
});
