import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const width of [320, 390, 430]) for (const theme of ['light', 'dark']) {
  test(`mobile chat stays centered with quiet corner controls ${width} ${theme}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 740 });
    await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
    const state = await workspace(page);
    state.complete('A centered explanation.\n\nHere is a useful response with enough text to wrap naturally on a phone.');
    await page.goto('/chat/polish-chat');
    const answer = page.getByRole('article', { name: 'Mentra response' }).last().locator('.markdown-content').first();
    await expect(answer).toBeVisible();
    const bounds = await answer.boundingBox();
    expect(Math.abs(bounds!.x - (width - bounds!.x - bounds!.width))).toBeLessThanOrEqual(2);
    const menu = page.getByRole('button', { name: 'Open navigation menu' });
    const bell = page.getByRole('link', { name: /^Notifications/ });
    const left = await menu.boundingBox(); const right = await bell.boundingBox();
    expect(left!.width).toBe(44); expect(right!.width).toBe(44);
    expect(left!.x).toBeLessThanOrEqual(8);
    expect(width - right!.x - right!.width).toBeLessThanOrEqual(8);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath('mobile-chat.png') });
    const composer = page.getByRole('textbox', { name: 'Ask Mentra anything' });
    await expect(composer).toHaveCSS('font-size', '16px');
    const form = page.getByRole('form', { name: 'Message Mentra' });
    const mic = page.getByRole('button', { name: 'Record voice message' });
    const send = page.getByRole('button', { name: 'Send message' });
    await expect(mic).toBeVisible();
    const compact = await form.boundingBox();
    expect(compact!.height).toBeLessThanOrEqual(56);
    const sendBefore = await send.boundingBox();
    await composer.focus();
    await expect(mic).toBeHidden();
    await composer.fill('Hello');
    expect((await form.boundingBox())!.height).toBeLessThanOrEqual(56);
    expect((await send.boundingBox())!.x).toBe(sendBefore!.x);
    await composer.fill('A longer message that should naturally wrap over several lines in the compact mobile composer. '.repeat(3));
    expect((await form.boundingBox())!.height).toBeGreaterThan(compact!.height);
    await composer.fill('');
    await composer.blur();
    await expect(mic).toBeVisible();
    expect((await form.boundingBox())!.height).toBeLessThanOrEqual(56);

    await page.setViewportSize({ width, height: 430 });
    await composer.fill('A longer draft\n'.repeat(20));
    const inputBounds = await composer.boundingBox();
    expect(inputBounds!.height).toBeLessThanOrEqual(130);
    expect(inputBounds!.y + inputBounds!.height).toBeLessThan(430);
    await menu.click();
    await expect(page.getByRole('dialog', { name: 'Main navigation' }).getByRole('button', { name: 'Close navigation menu' })).toBeVisible();
  });
}
