import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const theme of ['light', 'dark']) test(`welcome actions start a conversation and return to a fresh workspace in ${theme}`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
  await workspace(page);
  await page.goto('/');
  const request = page.waitForRequest(item => item.url().endsWith('/conversations/turns') && item.method() === 'POST');
  await page.getByRole('button', { name: 'Explain a concept', exact: true }).click();
  expect((await request).postDataJSON().content).toBe('Help me understand a concept. Ask me which topic to explore.');
  await expect(page.getByRole('log')).toBeVisible();
  await page.getByRole('button', { name: 'Start a new chat', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('learning today?');
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toHaveValue('');
});

test('welcome works with reduced motion and never requests a graphics context', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    Object.assign(window, { graphicsRequests: 0 });
    HTMLCanvasElement.prototype.getContext = function(type: string, ...args: unknown[]) {
      if (/webgl/.test(type)) { (window as unknown as { graphicsRequests: number }).graphicsRequests++; return null; }
      return Reflect.apply(original, this, [type, ...args]);
    } as typeof original;
  });
  await page.setViewportSize({ width: 390, height: 720 });
  await workspace(page);
  await page.goto('/');
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Keep this draft');
  await page.getByRole('button', { name: 'Open navigation menu' }).click();
  await page.getByRole('button', { name: 'Close navigation menu', exact: true }).last().click();
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toHaveValue('Keep this draft');
  expect(await page.evaluate(() => (window as unknown as { graphicsRequests: number }).graphicsRequests)).toBe(0);
});
