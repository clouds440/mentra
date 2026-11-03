import { expect, test, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { chooseOption } from './select-helpers';

async function setup(page: Page) {
  await workspace(page, false, true);
  await page.route('**/api/v1/rag/capabilities', route => route.fulfill({ json: { formats: ['pdf', 'docx', 'txt', 'png', 'py', 'Dockerfile'], max_upload_bytes: 2 * 1024 * 1024, max_pages: 200 } }));
  const creates: Record<string, unknown>[] = [];
  const contexts: Record<string, unknown>[] = [];
  await page.route('**/api/v1/files/uploads', route => route.fulfill({ json: { id: 'file-new', state: 'STAGED', filename: 'notes.txt', size_bytes: 24, purpose: 'library' } }));
  await page.route('**/api/v1/documents', route => {
    creates.push(route.request().postDataJSON());
    return route.fulfill({ json: { document_id: 'new-material', duplicate: false, job_id: 'job-new' } });
  });
  await page.route('**/api/v1/learning-contexts', route => {
    contexts.push(route.request().postDataJSON());
    return route.fulfill({ json: { context_id: 'created-context', name: 'Biology', status: 'ACTIVE' } });
  });
  return { creates, contexts };
}

for (const width of [390, 1440]) for (const theme of ['light', 'dark']) test(`library and upload layout at ${width}px in ${theme}`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.addInitScript(theme => localStorage.setItem('mentra-theme', theme), theme);
  await setup(page);
  await page.goto('/library');
  await expect(page.getByRole('link', { name: 'Motion and forces', exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath(`library-${theme}-${width}.png`), fullPage: true });
  await page.getByRole('button', { name: 'Add material', exact: true }).click();
  await expect(page.getByText('Drop a file to get started')).toBeVisible();
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'Chapter one revision notes with a long filename.txt', mimeType: 'text/plain', buffer: Buffer.from('Study these useful notes.') });
  await expect(page.getByText('Ready to upload', { exact: false })).toBeVisible();
  const footerBefore = await page.locator('.material-upload-footer').evaluate(node => (node as HTMLElement).offsetTop);
  await page.getByRole('radio', { name: 'Create new', exact: true }).check();
  await page.getByLabel('New context name', { exact: true }).fill('Biology');
  const footerAfter = await page.locator('.material-upload-footer').evaluate(node => (node as HTMLElement).offsetTop);
  expect(Math.abs(footerBefore - footerAfter)).toBeLessThan(2);
  await page.screenshot({ path: info.outputPath(`upload-${theme}-${width}.png`), fullPage: true });
  expect(await page.locator('.workspace-page').evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
});

test('existing and new context uploads keep the canonical request workflow', async ({ page }) => {
  const state = await setup(page);
  await page.goto('/library/new');
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Important revision notes') });
  await page.getByLabel('Material title', { exact: true }).fill('My notes');
  await chooseOption(page.getByLabel('Choose a learning context'), 'context-1');
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page).toHaveURL(/uploaded=accepted/);
  expect(state.creates[0]).toMatchObject({ file_id: 'file-new', title: 'My notes', context_ids: ['context-1'] });
  expect(state.contexts).toHaveLength(0);
  await page.goto('/library/new');
  await page.getByRole('radio', { name: 'Create new', exact: true }).check();
  await page.getByLabel('New context name').fill('Biology');
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('New biology notes') });
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page).toHaveURL(/uploaded=accepted/);
  expect(state.contexts).toHaveLength(1);
  expect(state.creates[1]).toMatchObject({ context_ids: ['created-context'] });
});

test('dropping files supports upload and rejects oversized and multi-file drops', async ({ page }) => {
  await setup(page); await page.goto('/library/new');
  // The loading skeleton also contains .file-dropzone; wait for the real form.
  await expect(page.getByRole('button', { name: 'Upload material', exact: true })).toBeVisible();
  const drop = page.locator('.file-dropzone');
  const files = await page.evaluateHandle(() => { const data = new DataTransfer(); data.items.add(new File(['Drop content'], 'dropped.txt', { type: 'text/plain' })); return data; });
  await drop.dispatchEvent('drop', { dataTransfer: files });
  await expect(page.getByText('dropped.txt', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Remove selected file' }).click();
  await expect(page.getByRole('button', { name: 'Upload material', exact: true })).toBeDisabled();
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'large.txt', mimeType: 'text/plain', buffer: Buffer.alloc(3 * 1024 * 1024) });
  await expect(page.getByRole('alert')).toContainText('exceeds the upload size limit');
  const multiple = await page.evaluateHandle(() => { const data = new DataTransfer(); for (const name of ['one.txt', 'two.txt']) data.items.add(new File(['content'], name)); return data; });
  await drop.dispatchEvent('drop', { dataTransfer: multiple });
  await expect(page.getByRole('alert')).toContainText('one file at a time');
});

test('failed upload retains the new context, file and retry identity without uploading twice', async ({ page }) => {
  const state = await setup(page);
  const attempts: Record<string, unknown>[] = [];
  let fileUploads = 0;
  page.on('request', request => { if (request.url().endsWith('/files/uploads')) fileUploads++; });
  await page.route('**/api/v1/documents', route => {
    attempts.push(route.request().postDataJSON());
    return attempts.length === 1 ? route.fulfill({ status: 503, json: { detail: 'Upload could not be saved.' } })
      : route.fulfill({ json: { document_id: 'new-material', duplicate: false, job_id: 'job-new' } });
  });
  await page.goto('/library/new');
  await page.getByRole('radio', { name: 'Create new', exact: true }).check();
  await page.getByLabel('New context name').fill('Biology');
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Revision notes') });
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Upload material', exact: true })).toBeEnabled();
  await expect(page.getByLabel('Choose a learning context')).toContainText('Biology');
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page).toHaveURL(/uploaded=accepted/);
  expect(state.contexts).toHaveLength(1);
  expect(fileUploads).toBe(1);
  expect(attempts[0]).toEqual(attempts[1]);
});
