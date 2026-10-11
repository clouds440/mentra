import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

test('web progress shows websites and favicon citations survive canonical reload', async ({ page, context }) => {
  // External favicon I/O is a controlled double; auth/chat/quota storage are real.
  // Playwright aborts every URL ending in /favicon.ico before user routes run.
  // Rewrite the image attribute in this test only so its fixture can exercise loading.
  await page.addInitScript(() => {
    const descriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src')!;
    Object.defineProperty(HTMLImageElement.prototype, 'src', { ...descriptor, set(value: string) {
      descriptor.set!.call(this, value.endsWith('/favicon.ico') ? `${value}?playwright-fixture=1` : value);
    } });
  });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).pathname !== '/favicon.ico') return route.continue();
    if (new URL(route.request().url()).hostname !== 'www.python.org') return route.abort();
    expect(route.request().headers()['referer']).toBeUndefined();
    expect(route.request().headers()['cookie']).toBeUndefined();
    return route.fulfill({ contentType: 'image/png', headers: { 'Access-Control-Allow-Origin': '*' },
      body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAJUlEQVR4nGMMqFjwn4ECwESJ5lEDIICJgULANGoAw2gYMFAeBgAA+gKHutRFVwAAAABJRU5ErkJggg==', 'base64') });
  });
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`web_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('a unique web search test passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Search python.org for the latest release');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Searching python.org', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('python.org', { exact: true }).first()).toBeVisible();
  const answer = page.getByRole('article', { name: 'Mentra response' });
  const inline = answer.getByRole('link', { name: 'Open web source W1: Python release information on www.python.org (new tab)' }).first();
  await expect(inline).toBeVisible();
  await expect(inline).toHaveAttribute('href', 'https://www.python.org/downloads/');
  await expect(inline).toHaveAttribute('target', '_blank');
  await expect(inline).toHaveAttribute('rel', 'noopener noreferrer');
  await expect(inline.locator('img')).toBeVisible();
  await expect(answer.getByRole('link', { name: 'Open web source W1:', exact: false })).toHaveCount(1);
  await answer.getByText('Web sources (2)', { exact: true }).click();
  await expect(answer.getByRole('link', { name: 'Open web source W1:', exact: false })).toHaveCount(2);
  await expect(answer).toContainText('Published Oct 8, 2026');
  await expect(answer).toContainText('Publication date unavailable');
  await expect(answer).toContainText('Asia/Karachi');
  await expect(answer).toContainText('Consulted · docs.python.org');
  await page.reload();
  await expect(inline).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Search python.org for the latest release');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(answer.last()).toContainText('Recently cached web results were reused');
  await page.setViewportSize({ width: 360, height: 740 });
  await answer.last().getByText('Web sources (2)', { exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  const latestCitation = answer.last().getByRole('link', { name: 'Open web source W1:', exact: false }).first();
  await latestCitation.focus();
  await expect(latestCitation).toBeFocused();
  await expect.poll(() => page.getByRole('complementary', { name: 'Main navigation' }).evaluate(node => node.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  await answer.last().getByText('Consulted · docs.python.org').scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'test-results/web-search-mobile.png', fullPage: true });
});
