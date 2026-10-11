import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const track = { stop() {}, onended: null };
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, writable: true,
      value: async () => ({ getTracks: () => [track], getAudioTracks: () => [track] }) });
    class Recorder {
      static isTypeSupported() { return true; }
      state = 'inactive'; mimeType = 'audio/webm';
      onstop: (() => void) | null = null;
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onerror = null;
      start() { this.state = 'recording'; }
      stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['audio'], { type: this.mimeType }) }); this.onstop?.(); }
    }
    Object.defineProperty(window, 'MediaRecorder', { value: Recorder });
  });
});

for (const width of [390, 1280]) test(`voice fills editable multilingual draft at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 844 });
  let requests = 0;
  await page.route('**/api/v1/speech/transcriptions', async route => {
    requests++; expect(route.request().postData()).toContain('audio');
    expect(route.request().postData()).not.toContain('name="language"');
    await route.fulfill({ json: { text: 'مجھے Newton’s second law سمجھائیں۔', language: 'ur' } });
  });
  await page.goto('/tests/voice-harness.html');
  const input = page.getByRole('textbox', { name: 'Ask Mentra anything' });
  await input.fill('My draft:');
  await expect(page.getByRole('combobox', { name: 'Spoken language' })).toHaveCount(0);
  const mic = page.getByRole('button', { name: 'Record voice message', exact: true });
  const send = page.getByRole('button', { name: 'Send message' });
  const left = await mic.boundingBox(), right = await send.boundingBox();
  expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x);
  await mic.click();
  await expect(page.getByText('30-second limit')).toHaveCount(0);
  await expect(page.getByLabel('Voice recording', { exact: true })).toBeVisible();
  await expect(send).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath('recording.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole('button', { name: 'Stop recording', exact: true }).click();
  await expect(input).toHaveValue('My draft: مجھے Newton’s second law سمجھائیں۔');
  await expect(page.getByTestId('sent')).toBeEmpty();
  await expect(input).toHaveAttribute('dir', 'auto');
  await input.fill('اشرح هذه equation'); await send.click();
  await expect(page.getByTestId('sent')).toHaveText('اشرح هذه equation');
  expect(requests).toBe(1);
});

test('a late transcription cannot fill a different chat', async ({ page }) => {
  let finish: () => void = () => {};
  const pending = new Promise<void>(resolve => { finish = resolve; });
  await page.route('**/api/v1/speech/transcriptions', async route => {
    await pending;
    await route.fulfill({ json: { text: 'Late response', language: 'en' } }).catch(() => {});
  });
  await page.goto('/tests/voice-harness.html');
  await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
  await page.getByRole('button', { name: 'Stop recording', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Transcribing…');
  await page.getByRole('button', { name: 'Switch chat' }).click();
  finish();
  await expect(page.getByRole('textbox')).toBeEmpty();
  await expect(page.getByTestId('sent')).toBeEmpty();
});

test('recording stops automatically without displaying the cap', async ({ page }) => {
  await page.clock.install();
  await page.route('**/api/v1/speech/transcriptions', route => route.fulfill({ json: { text: 'Recorded question', language: 'en' } }));
  await page.goto('/tests/voice-harness.html');
  await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
  await page.clock.fastForward(30_200);
  await expect(page.getByRole('textbox')).toHaveValue('Recorded question');
  await expect(page.getByTestId('sent')).toBeEmpty();
  await expect(page.getByText(/30-second limit|Auto detect/)).toHaveCount(0);
});

test('permission denial, cancellation, retry and switching chats', async ({ page }) => {
  await page.goto('/tests/voice-harness.html');
  await page.evaluate(() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('denied', 'NotAllowedError'); }; });
  await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('permission was denied');
  await page.reload();
  let requests = 0;
  await page.route('**/api/v1/speech/transcriptions', async route => {
    requests++;
    if (requests === 1) await route.fulfill({ status: 429, json: { error: { message: 'Voice input is busy.' } } });
    else await route.fulfill({ json: { text: 'Hello', language: 'en' } });
  });
  await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel voice input' }).click();
  expect(requests).toBe(0);
  await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
  await page.getByRole('button', { name: 'Stop recording', exact: true }).click();
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByRole('textbox')).toHaveValue('Hello');
  await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
  await page.getByRole('button', { name: 'Switch chat' }).click();
  await expect(page.getByRole('textbox')).toBeEmpty();
  await expect(page.getByLabel('Voice recording', { exact: true })).toHaveCount(0);
});
