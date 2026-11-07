import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import AxeBuilder from '@axe-core/playwright';

const variants = [
    { width: 390, height: 844, theme: 'light' },
    { width: 768, height: 1024, theme: 'light' },
    { width: 1440, height: 1000, theme: 'light' },
    { width: 1440, height: 1000, theme: 'dark' },
    { width: 2560, height: 1440, theme: 'light' },
];
for (const variant of variants) test(`product screens remain usable at ${variant.width}px in ${variant.theme}`, async ({ page }, info) => {
  test.setTimeout(60000);
  await workspace(page, false, true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const compare = process.env.DESIGN_CAPTURE_BASELINE && [390, 1440].includes(variant.width) && variant.theme === 'light';
  const origins = compare ? ['http://127.0.0.1:15174', ''] : [''];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const origin of origins) {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.addInitScript(theme => localStorage.setItem('mentra-theme', theme), variant.theme);
    for (const route of ['/', '/library', '/progress', '/assessments', '/settings']) {
      await page.goto(`${origin}${route}`);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.fonts.check('400 16px "Inter Variable"'))).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), route).toBe(true);
      if (route === '/') await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeInViewport();
      await page.screenshot({ path: info.outputPath(`${origin ? 'before' : 'after'}-${route === '/' ? 'chat' : route.slice(1)}-${variant.width}-${variant.theme}.png`) });
    }
  }
  expect(errors).toEqual([]);
});

for (const width of [390, 1440]) test(`account entry stays readable and validates fields at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Sign in required' } }));
  await page.goto('/register');
  await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible();
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Username' })).toBeFocused();
  await expect(page.getByText('Use at least 12 characters for your password.')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath(`register-${width}.png`) });
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(accessibility.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))).toEqual([]);
  await page.screenshot({ path: info.outputPath(`login-${width}.png`) });
});

for (const theme of ['light', 'dark']) test(`workspace has no automated WCAG A/AA violations in ${theme}`, async ({ page }) => {
  test.setTimeout(60000);
  await workspace(page, false, true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
  for (const route of ['/', '/library', '/progress', '/assessments', '/settings']) {
    await page.goto(route);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) })), route).toEqual([]);
  }
});

test('keyboard tabs and switches update the intended preference and preserve focus', async ({ page }) => {
  await workspace(page);
  let enabled = false;
  await page.route('**/api/v1/notifications/preferences', async route => {
    if (route.request().method() !== 'GET') enabled = route.request().postDataJSON().enabled;
    return route.fulfill({ json: { enabled, disabled_kinds: [], revision: 1 } });
  });
  await page.goto('/settings');
  const profile = page.getByRole('tab', { name: 'Profile & preferences' });
  await profile.focus();
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: 'Archived chats', exact: true })).toBeFocused();
  await page.keyboard.press('ArrowLeft');
  const notifications = page.getByRole('tab', { name: 'Notifications', exact: true });
  await expect(notifications).toBeFocused();
  await expect(notifications).toHaveAttribute('aria-selected', 'true');
  const toggle = page.getByRole('switch', { name: 'Enable notifications', exact: true });
  await expect(toggle).not.toBeChecked();
  await toggle.focus();
  await page.keyboard.press('Space');
  await expect(toggle).toBeChecked();
  await page.getByRole('button', { name: 'Save settings', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Settings saved.' })).toBeVisible();
  expect(enabled).toBe(true);
});

test('empty chat offers clear starting actions without a graphics context', async ({ page }) => {
  await workspace(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 720 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: /Study my material/ })).toBeVisible();
  await page.getByRole('button', { name: /Study my material/ }).click();
  await expect(page.getByRole('dialog', { name: 'Choose study material' })).toBeVisible();
  await expect(page.locator('.light-rays, .chat-welcome canvas')).toHaveCount(0);
});
