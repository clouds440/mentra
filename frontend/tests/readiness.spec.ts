import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const unavailable of ['missing', 'blocked'] as const) {
  test(`authenticated workspace works when tab messaging is ${unavailable}`, async ({ page }) => {
    const failures: string[] = [];
    page.on('pageerror', error => failures.push(error.message));
    await page.addInitScript(mode => {
      Object.defineProperty(window, 'BroadcastChannel', { configurable: true, value: mode === 'missing' ? undefined : class {
        constructor() { throw new DOMException('Blocked by browser policy', 'SecurityError'); }
      } });
    }, unavailable);
    await workspace(page);
    await page.goto('/chat/polish-chat');
    await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeEnabled();
    await expect(page.getByRole('link', { name: /A long conversation about understanding motion/ })).toBeVisible();
    await page.goto('/library');
    await expect(page.getByRole('heading', { name: 'Library', exact: true })).toBeVisible();
    expect(failures).toEqual([]);
  });
}

test('upload receipts isolate accounts, filenames and aborted retries in a real browser', async ({ page }) => {
  await workspace(page);
  let uploads = 0;
  await page.route('**/api/v1/files/uploads', route => route.fulfill({ json: {
    id: `upload-${++uploads}`, filename: 'source.txt', size_bytes: 9, media_type: 'text/plain', state: 'STAGED', purpose: 'chat',
  } }));
  await page.goto('/chat/polish-chat');
  const result = await page.evaluate(async () => {
    const path = '/src/services/files.ts';
    const files = await import(/* @vite-ignore */ path);
    const blob = new Blob(['synthetic']);
    files.setUploadOwner('account-a');
    const first = await files.uploadFile(blob, 'source.txt', 'chat');
    const cached = await files.uploadFile(blob, 'source.txt', 'chat');
    const renamed = await files.uploadFile(blob, 'renamed.txt', 'chat');
    files.setUploadOwner('account-b');
    const second = await files.uploadFile(blob, 'source.txt', 'chat');
    const clock = performance.now.bind(performance);
    Object.defineProperty(performance, 'now', { configurable: true, value: () => clock() + 24 * 60 * 60_000 });
    let expired;
    try { expired = await files.uploadFile(blob, 'source.txt', 'chat'); }
    finally { Object.defineProperty(performance, 'now', { configurable: true, value: clock }); }
    const controller = new AbortController(); controller.abort();
    let aborted = false;
    try { await files.uploadFile(blob, 'source.txt', 'chat', controller.signal); }
    catch (error) { aborted = error instanceof DOMException && error.name === 'AbortError'; }
    return { first: first.id, cached: cached.id, renamed: renamed.id, second: second.id, expired: expired.id, aborted };
  });
  expect(result).toEqual({ first: 'upload-1', cached: 'upload-1', renamed: 'upload-2', second: 'upload-3', expired: 'upload-4', aborted: true });
  expect(uploads).toBe(4);
});
