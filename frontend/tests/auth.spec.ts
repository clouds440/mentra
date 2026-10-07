import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

const password = 'a long unique passphrase';
const username = () => `learner_${randomUUID().slice(0, 8)}`;

async function signUp(page: Page, name: string) {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(name);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
}

async function openAccountMenu(page: Page) {
  await page.getByRole('button', { name: /^Account menu/ }).click();
}

test('registration uses real auth, HTTP-only cookies, refresh, and return visits', async ({ page, context, browser }) => {
  const name = username();
  await signUp(page, name);
  await openAccountMenu(page);
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  const cookies = await context.cookies('http://127.0.0.1:18003/api/v1/auth/me');
  const session = cookies.find((cookie) => cookie.name === 'mentra_session');
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe('Lax');
  expect(session?.expires).toBeGreaterThan(Date.now() / 1000 + 365 * 86400);
  expect(await page.evaluate(() => document.cookie)).not.toContain('mentra_session');
  expect(await page.evaluate(() => ({ ...localStorage }))).not.toHaveProperty('access_token');
  await page.reload();
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
  await page.goto('/login');
  await expect(page).toHaveURL(/\/$/);
  // A new browser context with persisted browser state reproduces a later visit.
  const saved = await context.storageState();
  const returning = await browser.newContext({ storageState: saved });
  try {
    const revisit = await returning.newPage();
    await revisit.goto('http://127.0.0.1:15173/progress');
    await expect(revisit.getByRole('heading', { name: 'Progress', exact: true })).toBeVisible();
    await expect(revisit).toHaveURL(/\/progress$/);
  } finally { await returning.close(); }
});

test('protected routes preserve destination and existing-user login restores it', async ({ page }) => {
  const name = username();
  await signUp(page, name);
  await openAccountMenu(page);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/library');
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Username', { exact: true }).fill(name.toUpperCase());
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/library$/);
  await expect(page.getByRole('heading', { name: 'Library', exact: true })).toBeVisible();
});

test('logout revokes real server access, clears cookies, and syncs another tab', async ({ page, context }) => {
  await signUp(page, username());
  const second = await context.newPage();
  await second.goto('/settings');
  await expect(second.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  await openAccountMenu(page);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(second).toHaveURL(/\/login$/);
  expect((await context.cookies()).find((cookie) => cookie.name === 'mentra_session')).toBeUndefined();
  const response = await context.request.get('http://127.0.0.1:18003/api/v1/auth/me');
  expect(response.status()).toBe(401);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
});

test('validation, password visibility, duplicate accounts, and incorrect passwords', async ({ page }) => {
  const name = username();
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill('invalid space');
  await page.getByLabel('Password', { exact: true }).fill('short');
  await page.getByRole('button', { name: 'Show password' }).click();
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text');
  await page.getByRole('button', { name: 'Hide password' }).click();
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByText('Use at least 12 characters for your password.')).toBeVisible();
  await expect(page.getByLabel('Username', { exact: true })).toBeFocused();
  await signUp(page, name);
  await openAccountMenu(page);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByRole('link', { name: 'Create an account' }).click();
  await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible();
  await page.getByLabel('Username', { exact: true }).fill(name);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByText('That username is already registered.')).toBeVisible();
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByLabel('Username', { exact: true }).fill(name);
  await page.getByLabel('Password', { exact: true }).fill('incorrect');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('That username or password isn’t correct.');
  await expect(page).toHaveURL(/\/login$/);
});

test('background network failure keeps a known session authenticated', async ({ page, context }) => {
  await signUp(page, username());
  await context.setOffline(true);
  // Client-side navigation keeps the app assets loaded while session restoration fails.
  await page.evaluate(() => { window.dispatchEvent(new FocusEvent('focus')); });
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
  await context.setOffline(false);
  await page.reload();
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
});

test('failed logout retains the session and allows retry', async ({ page, context }) => {
  await signUp(page, username());
  await context.setOffline(true);
  await openAccountMenu(page);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Couldn’t reach Mentra. Check your connection and try again.');
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
  await context.setOffline(false);
  await openAccountMenu(page);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
});

test('initial network failure offers retry and restores the real session', async ({ page }) => {
  await signUp(page, username());
  // Block transport until retry; successful auth requests still use the real backend.
  await page.route('**/api/v1/auth/me', (route) => route.abort('connectionfailed'));
  await page.reload();
  await expect(page.getByRole('heading', { name: 'We couldn’t open your workspace' })).toBeVisible();
  await page.unroute('**/api/v1/auth/me');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
});

test('every workspace route requires a session and registration preserves the destination', async ({ page }) => {
  for (const path of ['/', '/library', '/progress', '/assessments', '/settings', '/unknown']) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  }
  await page.goto('/assessments?practice=1#start');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByRole('link', { name: 'Create an account' }).click();
  await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible();
  await page.getByLabel('Username', { exact: true }).fill(username());
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await expect(page).toHaveURL(/\/assessments\?practice=1#start$/);
});

test('mobile navigation exposes logout and auth stays usable on a short screen', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 568 });
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(username());
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole('button', { name: 'Open navigation menu' }).click();
  await openAccountMenu(page);
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Main navigation' })).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 0)');
  await page.screenshot({ path: testInfo.outputPath('mobile-logout.png') });
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

for (const theme of ['light', 'dark'] as const) {
  test(`auth fits mobile and desktop in ${theme} mode and respects reduced motion`, async ({ page }, testInfo) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    for (const width of [320, 768, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/register');
      await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      const duration = await page.locator('.auth-enter').evaluate((element) => getComputedStyle(element).animationDuration);
      expect(parseFloat(duration)).toBeLessThanOrEqual(0.01);
      await page.screenshot({ path: testInfo.outputPath(`register-${theme}-${width}.png`), fullPage: true });
    }
  });
}
