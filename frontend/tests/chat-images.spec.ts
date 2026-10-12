import { test, expect, type Page } from '@playwright/test';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6YZsAAAAASUVORK5CYII=', 'base64');
const image = (number: number) => ({ name: `image-${number}.png`, mimeType: 'image/png', buffer: png });

async function pasteFiles(page: Page, files: { name: string; mimeType: string; buffer: Buffer }[], itemsOnly = false) {
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).evaluate((input, payload) => {
    const clipboard = new DataTransfer();
    for (const file of payload.files) clipboard.items.add(new File([Uint8Array.from(atob(file.data), c => c.charCodeAt(0))], file.name, { type: file.mimeType }));
    if (payload.itemsOnly) Object.defineProperty(clipboard, 'files', { value: [] });
    input.dispatchEvent(new ClipboardEvent('paste', { clipboardData: clipboard, bubbles: true, cancelable: true }));
  }, { files: files.map(file => ({ name: file.name, mimeType: file.mimeType, data: file.buffer.toString('base64') })), itemsOnly });
}

async function setup(page: Page, failSecondUpload = false) {
  const conversation = { id: 'image-chat', title: 'Image discussion', revision: 1, message_count: 0,
    selection: { mode: 'STANDARD' }, created_at: '2026-10-12T00:00:00Z', updated_at: '2026-10-12T00:00:00Z', deleted_at: null };
  const files: { id: string; filename: string; size_bytes: number }[] = [];
  const items: Record<string, unknown>[] = [];
  const sent: Record<string, unknown>[] = [];
  let uploads = 0, rejected = false;
  const snapshot = () => ({ conversation, items, has_more: false, next_cursor: null, turn: null });
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith('/source')) return route.fulfill({ contentType: 'image/png', body: png });
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = { learner_id: 'image-user', username: 'learner', user_id: null, provider: null };
    else if (path.endsWith('/student-profile')) body = { learner_id: 'image-user', details: { education_level: 'college', field_of_study: 'Physics', learning_goal: 'Understand motion', learning_preference: 'balanced', explanation_depth: 'standard' },
      estimates: Object.fromEntries(['overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity'].map(key => [key, { value: null, confidence: 0, evidence_count: 0 }])),
      onboarding_phase: 'complete', calibration_status: 'skipped', evaluation_status: 'not_started', version: 1, context_version: 1 };
    else if (path.endsWith('/conversations/sync')) body = { reset: false, cursor: conversation.revision, has_more: false, conversations: [conversation], deleted_ids: [], list_cursor: null };
    else if (path.endsWith('/status')) body = snapshot();
    else if (path.endsWith('/chat-attachments') && request.method() === 'POST') {
      uploads++;
      if (failSecondUpload && uploads === 2 && !rejected) {
        rejected = true;
        return route.fulfill({ status: 503, json: { error: { code: 'UPLOAD_FAILED', message: 'Try this upload again.' } } });
      }
      const file = { id: `file-${files.length + 1}`, filename: `image-${files.length + 1}.png`, size_bytes: png.length };
      files.push(file); body = file;
    } else if (path.endsWith('/conversations/turns')) {
      const payload = request.postDataJSON(); sent.push(payload);
      items.push({ id: `user-${sent.length}`, conversation_id: conversation.id, sequence: items.length + 1, role: 'user', content: payload.content,
        attachments: files.filter(file => payload.attachment_ids.includes(file.id)), created_at: conversation.created_at });
      items.push({ id: `reply-${sent.length}`, conversation_id: conversation.id, sequence: items.length + 1, role: 'assistant', content: 'Here is the image comparison.', created_at: conversation.created_at });
      conversation.revision++; conversation.message_count = items.length; body = snapshot();
    } else if (path.includes('/chat-attachments/')) body = { ...files.find(file => path.includes(file.id)), ready: true, warnings: [], error: null, library_result: null };
    else if (path.endsWith('/notifications/unread-count')) body = { count: 0 };
    else if (path.endsWith('/assessments/preferences')) body = { auto_add: false, revision: 1 };
    await route.fulfill({ json: body });
  });
  await page.goto('/chat/image-chat');
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeEnabled({ timeout: 15_000 });
  return { sent, uploads: () => uploads };
}

for (const width of [1280, 390]) test(`three images stay staged until Send and survive reopening at width ${width}`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  const state = await setup(page);
  await page.getByLabel('Upload chat files').setInputFiles([image(1), image(2), image(3)]);
  await expect(page.getByLabel('Attached files').getByRole('img')).toHaveCount(3);
  expect(state.uploads()).toBe(0); expect(state.sent).toHaveLength(0);
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeFocused();
  await page.getByLabel('Upload chat files').setInputFiles(image(4));
  await expect(page.getByRole('alert')).toContainText(/three images|at most three images/);
  await expect(page.getByLabel('Attached files').getByRole('img')).toHaveCount(3);
  await page.getByRole('button', { name: 'Remove image-3.png', exact: true }).click();
  await page.getByLabel('Upload chat files').setInputFiles(image(3));
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Compare the three diagrams.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('article', { name: 'Mentra response' })).toContainText('image comparison');
  expect(state.uploads()).toBe(3);
  expect(state.sent[0].content).toBe('Compare the three diagrams.');
  expect(state.sent[0].attachment_ids).toHaveLength(3);
  await expect(page.getByLabel('Attachment image-1.png').getByRole('img')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('article', { name: 'Your message' })).toContainText('Compare the three diagrams.');
  for (const number of [1, 2, 3]) await expect(page.getByLabel(`Attachment image-${number}.png`).getByRole('img')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('native clipboard image paste stages once and leaves the typed query intact', async ({ page }) => {
  const state = await setup(page);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.evaluate(async () => {
    const canvas = document.createElement('canvas'); canvas.width = 100; canvas.height = 100;
    const context = canvas.getContext('2d')!; context.fillStyle = '#478a78'; context.fillRect(0, 0, 100, 100);
    const picture = await new Promise<Blob>(resolve => canvas.toBlob(blob => resolve(blob!), 'image/png'));
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': picture })]);
  });
  const input = page.getByRole('textbox', { name:'Ask Mentra anything' });
  await input.fill('Explain this diagram.');
  await input.press('Control+V');
  await expect(page.getByLabel('Attached files').getByRole('img')).toHaveCount(1);
  await expect(input).toHaveValue('Explain this diagram.');
  expect(state.uploads()).toBe(0); expect(state.sent).toHaveLength(0);
});

test('pasted documents and item-only clipboard files append to the same staged attachments', async ({ page }) => {
  const state = await setup(page);
  await page.getByLabel('Upload chat files').setInputFiles(image(1));
  await pasteFiles(page, [{name:'notes.pdf', mimeType:'application/pdf', buffer:Buffer.from('%PDF-1.4 test')}]);
  await pasteFiles(page, [image(2)], true);
  const attachments = page.getByRole('form', { name:'Message Mentra' }).getByLabel('Attached files');
  await expect(attachments.locator('li')).toHaveCount(3);
  await expect(attachments.getByRole('img')).toHaveCount(2);
  await expect(attachments).toContainText('notes.pdf');
  expect(state.uploads()).toBe(0); expect(state.sent).toHaveLength(0);
  await attachments.getByRole('button', { name:'Remove notes.pdf', exact:true }).click();
  await expect(attachments.locator('li')).toHaveCount(2);
});

test('clipboard attachments respect shared image and total file limits', async ({ page }) => {
  await setup(page);
  await page.getByLabel('Upload chat files').setInputFiles([image(1), image(2), image(3)]);
  await pasteFiles(page, [image(4)]);
  await expect(page.getByRole('alert')).toContainText('three images');
  await expect(page.getByLabel('Attached files').getByRole('img')).toHaveCount(3);
  await pasteFiles(page, [{name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('Notes')}]);
  await expect(page.getByLabel('Attached files').locator('li')).toHaveCount(4);
  await pasteFiles(page, [{name:'extra.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4')}]);
  await expect(page.getByRole('alert')).toContainText('four files');
  await expect(page.getByLabel('Attached files').locator('li')).toHaveCount(4);
});

test('plain text paste keeps normal editing behavior', async ({ page }) => {
  await setup(page);
  await page.context().grantPermissions(['clipboard-read','clipboard-write']);
  await page.evaluate(() => navigator.clipboard.writeText('pasted text'));
  const input = page.getByRole('textbox', { name:'Ask Mentra anything' });
  await input.fill('Before '); await input.press('Control+V');
  await expect(input).toHaveValue('Before pasted text');
  await expect(page.getByLabel('Attached files')).toHaveCount(0);
});

for (const files of [false, true]) test(`sending ${files ? 'attachments' : 'text'} never adds a skeleton to the composer`, async ({ page }) => {
  await setup(page);
  let release!: () => void, started!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  const requested = new Promise<void>(resolve => { started = resolve; });
  await page.route(files ? '**/api/v1/chat-attachments' : '**/api/v1/conversations/turns', async route => {
    started(); await pending; await route.fallback();
  });
  if (files) await pasteFiles(page, [image(1)]);
  const composer = page.getByRole('form', { name:'Message Mentra' });
  await composer.getByRole('textbox').fill('Explain this.');
  const height = await composer.evaluate(el => el.getBoundingClientRect().height);
  await composer.getByRole('button', { name:'Send message', exact:true }).click();
  await requested;
  try {
    await expect(composer.getByRole('status', { name:'Loading' })).toHaveCount(0);
    expect(await composer.evaluate(el => el.getBoundingClientRect().height)).toBeCloseTo(height, 0);
    if (files) {
      await expect(composer.getByLabel('Attached files').getByRole('img')).toHaveCount(1);
      await pasteFiles(page, [image(2)]);
      await expect(composer.getByLabel('Attached files').getByRole('img')).toHaveCount(1);
    }
  } finally { release(); }
  await expect(page.getByRole('article', { name:'Mentra response' })).toBeVisible();
});

test('failed uploads retain staged images and query, and retry reuses completed upload', async ({ page }) => {
  const state = await setup(page, true);
  await page.getByLabel('Upload chat files').setInputFiles([image(1), image(2)]);
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Explain both images.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toHaveValue('Explain both images.');
  await expect(page.getByLabel('Attached files').getByRole('img')).toHaveCount(2);
  expect(state.sent).toHaveLength(0);
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('article', { name: 'Mentra response' })).toBeVisible();
  expect(state.uploads()).toBe(3); expect(state.sent[0].attachment_ids).toEqual(['file-1', 'file-2']);
});

for (const width of [1280, 390]) test(`compact attachments fit inside composer without cropping at ${width}`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 700 });
  await setup(page);
  const portrait = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 720; canvas.height = 1920;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#478a78'; context.fillRect(0, 0, 720, 1920);
    context.fillStyle = '#fff'; context.fillRect(0, 0, 720, 100); context.fillRect(0, 1820, 720, 100);
    return canvas.toDataURL().split(',')[1];
  });
  await page.getByLabel('Upload chat files').setInputFiles([
    { name: 'portrait.png', mimeType: 'image/png', buffer: Buffer.from(portrait, 'base64') },
    { name: 'study-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Study notes') },
  ]);
  const composer = page.getByRole('form', { name: 'Message Mentra' });
  const staged = composer.getByLabel('Attached files');
  await expect(staged.getByRole('img')).toBeVisible();
  const bounds = await composer.evaluate(form => {
    const image = form.querySelector('img')!;
    const preview = image.getBoundingClientRect();
    const frame = image.parentElement!.getBoundingClientRect();
    const text = form.querySelector('textarea')!.getBoundingClientRect();
    const rect = form.getBoundingClientRect();
    return { ratio: preview.width / preview.height, height: preview.height, padding: frame.width - preview.width,
      enclosed: frame.top >= rect.top && frame.bottom < text.top && text.bottom < rect.bottom,
      overflow: document.documentElement.scrollHeight > innerHeight + 1 };
  });
  expect(bounds.ratio).toBeCloseTo(720 / 1920, 2);
  expect(bounds.height).toBeLessThanOrEqual(96);
  expect(bounds.padding).toBeLessThanOrEqual(2);
  expect(bounds.enclosed).toBe(true); expect(bounds.overflow).toBe(false);
  await expect(staged.getByRole('button', { name: 'Remove portrait.png' })).toHaveText('');
  await page.screenshot({ path: info.outputPath('composer-previews.png') });
  await staged.getByRole('button', { name: 'Remove portrait.png' }).click();
  await expect(staged.getByRole('img')).toHaveCount(0);
  await expect(staged).toContainText('study-notes.txt');
});
