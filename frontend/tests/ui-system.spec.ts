import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

async function register(page: Page) {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`ui_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('a unique shared UI passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
}

test('portaled dropdowns support keyboard, multiselect, anchoring and dismissal', async ({ page }) => {
  await register(page);
  for (const name of ['Algebra', 'Physics']) {
    const response = await page.request.post('http://127.0.0.1:18003/api/v1/learning-contexts', {
      headers: { Origin: 'http://127.0.0.1:15173' }, data: { name, activate: true },
    });
    expect(response.ok()).toBeTruthy();
  }
  await page.getByRole('button', { name: 'Account menu', exact: false }).click();
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Edit profile', exact: true }).click();
  const level = page.getByRole('combobox', { name: 'Education level', exact: true });
  await level.focus(); await level.press('ArrowDown');
  const list = page.getByRole('listbox', { name: 'Education level options' });
  await expect(list).toBeVisible();
  expect(await list.evaluate(node => node.parentElement === document.body)).toBe(true);
  const triggerBox = await level.boundingBox(); const panelBox = await list.boundingBox();
  expect(panelBox!.y).toBeGreaterThanOrEqual(triggerBox!.y + triggerBox!.height);
  await level.press('End'); await level.press('Enter'); await expect(list).toHaveCount(0);
  await level.click(); await level.press('Escape'); await expect(level).toBeFocused();
  await expect(list).toHaveCount(0);
  await page.goto('/');
  await page.getByText('Use relevant study material automatically', { exact: true }).click();
  const sources = page.getByRole('combobox', { name: 'Study sources', exact: true });
  await sources.click(); await page.getByRole('option', { name: 'Choose learning contexts', exact: true }).click();
  const contexts = page.getByRole('combobox', { name: 'Selected learning contexts', exact: true });
  await contexts.click();
  const choices = page.getByRole('listbox', { name: 'Selected learning contexts options' });
  await expect(choices).toHaveAttribute('aria-multiselectable', 'true');
  await choices.getByRole('option', { name: /Algebra/ }).click();
  await choices.getByRole('option', { name: /Physics/ }).click();
  await expect(contexts).toContainText('Algebra'); await expect(contexts).toContainText('Physics');
  await choices.getByRole('option', { name: /Algebra/ }).click();
  await expect(contexts).not.toContainText('Algebra');
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).click();
  await expect(choices).toHaveCount(0);
  await page.goto('/events?event=00000000-0000-0000-0000-000000000001');
  await expect(page).toHaveURL(/\/progress\?event=.*tab=events/);
  await expect(page.getByRole('tab', { name: 'Events', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('link', { name: 'Events', exact: true })).toHaveCount(0);
});

for (const theme of ['light', 'dark'] as const) {
  test(`shared surfaces and file picker fit mobile in ${theme} mode`, async ({ page }, testInfo) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 390, height: 844 });
    await register(page);
    await page.goto('/library');
    await expect(page.getByRole('heading', { name: 'Library', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Upload file', exact: true })).toBeVisible();
    const file = page.getByLabel('File', { exact: true });
    expect(await file.evaluate(node => getComputedStyle(node).clip !== 'auto')).toBe(true);
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'Upload file', exact: true }).click();
    await (await chooser).setFiles({ name: 'chapter.txt', mimeType: 'text/plain', buffer: Buffer.from('Algebra notes') });
    await expect(page.getByText('chapter.txt', { exact: true })).toBeVisible();
    const context = page.getByRole('form', { name: 'Add material' }).getByRole('combobox', { name: 'Learning context', exact: true });
    await context.click();
    const panel = page.getByRole('listbox', { name: 'Learning context options' });
    await expect(panel).toBeVisible();
    const rect = await panel.boundingBox();
    expect(rect!.x).toBeGreaterThanOrEqual(12); expect(rect!.x + rect!.width).toBeLessThanOrEqual(378);
    expect(await panel.evaluate(node => getComputedStyle(node).backgroundColor)).not.toBe(await page.locator('body').evaluate(node => getComputedStyle(node).backgroundColor));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`shared-controls-${theme}.png`), fullPage: true });
    await context.press('Escape');
    await page.goto('/notifications');
    await expect(page.getByRole('switch', { name: 'Unread only', exact: true })).toBeVisible();
    await page.getByRole('switch', { name: 'Unread only', exact: true }).check();
    await page.goto('/progress?tab=events');
    await expect(page.getByRole('button', { name: 'New event', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`progress-events-${theme}.png`), fullPage: true });
  });
}
