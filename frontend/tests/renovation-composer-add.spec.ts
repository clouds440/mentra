import { expect, test } from '@playwright/test';
import { richChat } from './renovation-rich-fixtures';

const context = { context_id: 'physics', name: 'Physics', status: 'ACTIVE' };
const materials = ['Motion notes', 'Energy notes', 'Gravity notes'].map((title, index) => ({
  id: 'notes-' + index, title, filename: title + '.pdf', context_ids: [context.context_id],
  archived: false, active_generation_id: 'generation-' + index,
}));

for (const width of [390, 1440]) test('composer plus stages multiple removable references at ' + width, async ({ page }) => {
  await page.setViewportSize({ width, height: 850 });
  await richChat(page);
  await page.route('**/api/v1/documents/page?**', route => {
    const query = new URL(route.request().url()).searchParams.get('query')?.toLowerCase() ?? '';
    const items = materials.filter(item => item.title.toLowerCase().includes(query));
    return route.fulfill({ json: { items, total: items.length, offset: 0, limit: 25, contexts: [context] } });
  });
  await page.goto('/chat/polish-chat');
  const plus = page.getByRole('button', { name: 'Add to message', exact: true });
  const textarea = page.getByRole('textbox', { name: 'Ask Mentra anything' });
  const form = page.getByRole('form', { name: 'Message Mentra' });
  const references = form.getByRole('list', { name: 'Referenced materials' });
  await expect(plus).toHaveCount(1);
  await expect(form.getByRole('button', { name: 'Attach files' })).toHaveCount(0);
  await plus.click();
  const menu = page.getByRole('menu', { name: 'Add to message' });
  await expect(menu.getByRole('menuitem')).toHaveText(['Attach files', 'Reference material', 'Camera']);
  await expect(menu.getByRole('menuitem', { name: 'Attach files' })).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  const picker = page.getByRole('dialog', { name: 'Choose study material' });
  const search = picker.getByRole('searchbox', { name: 'Search study material' });
  await expect(search).toBeFocused();
  await search.fill('energy');
  await expect(picker.getByRole('option')).toHaveCount(1);
  await search.press('Enter');
  await expect(references).toContainText('Energy notes');
  await textarea.fill('Compare @motion');
  await picker.getByRole('option', { name: /Motion notes/ }).click();
  await expect(textarea).toHaveValue('Compare ');
  await expect(references.getByRole('listitem')).toHaveCount(2);
  await textarea.fill('Compare @gravity');
  await picker.getByRole('option', { name: /Gravity notes/ }).click();
  await references.getByRole('button', { name: 'Remove reference to Energy notes' }).click();
  await expect(references.getByRole('listitem')).toHaveCount(2);
  await textarea.fill('Compare these notes');
  const sent = page.waitForRequest(request => request.url().endsWith('/conversations/turns') && request.method() === 'POST');
  await form.getByRole('button', { name: 'Send message' }).click();
  expect((await sent).postDataJSON()).toMatchObject({ content: 'Compare these notes', retrieval: {
    mode: 'SOURCE_SPECIFIC', document_ids: ['notes-0', 'notes-2'],
  } });
});

test('camera captures into the existing attachment tray and releases its stream', async ({ page }) => {
  await richChat(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => {
      const canvas = document.createElement('canvas');
      canvas.width = 320; canvas.height = 240;
      const draw = canvas.getContext('2d')!;
      const stream = canvas.captureStream(15);
      const timer = window.setInterval(() => draw.fillRect(0, 0, 320, 240), 50);
      const track = stream.getVideoTracks()[0];
      const stop = track.stop.bind(track);
      track.stop = () => { clearInterval(timer); stop(); document.body.dataset.cameraReleased = 'true'; };
      return stream;
    } });
  });
  await page.goto('/chat/polish-chat');
  const plus = page.getByRole('button', { name: 'Add to message', exact: true });
  await plus.click();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('menuitem', { name: 'Attach files' }).click();
  await (await chooser).setFiles([]);
  await plus.click();
  await page.getByRole('menuitem', { name: 'Camera' }).click();
  const camera = page.getByRole('dialog', { name: 'Take a photo' });
  await camera.getByRole('button', { name: 'Capture photo' }).click();
  await expect(camera).toHaveCount(0);
  await expect(page.getByRole('list', { name: 'Attached files' }).getByRole('img', { name: 'Preview of Camera photo.jpg' })).toBeVisible();
  await expect(page.locator('body')).toHaveAttribute('data-camera-released', 'true');
});
