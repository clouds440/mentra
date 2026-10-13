import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const theme of ['light', 'dark']) for (const width of [320, 390, 768, 1440]) {
  test(`workspace route matrix ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
    await workspace(page, false, true);
    const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
    for (const [route, title] of [['/chat/polish-chat', ''], ['/library', 'Library'], ['/library/new', 'Add material'], ['/assessments', 'Assessments'], ['/assessments?tab=create', 'Create assessment'], ['/progress', 'Progress'], ['/progress?tab=events', 'Events'], ['/notifications', 'Notifications'], ['/settings', 'Settings']]) {
      await page.goto(route);
      await expect(page.getByRole('main')).toBeVisible();
      if (route.startsWith('/chat')) await expect(page.getByLabel('Ask Mentra anything')).toBeVisible();
      else { await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible(); await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1); }
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(route.replace(/[^a-z0-9]/gi, '-') + '.png'), animations: 'disabled' });
    }
    expect(errors).toEqual([]);
  });
}
