import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

test.skip(process.env.MENTRA_LAUNCH_HTTPS !== 'true', 'Requires the isolated local TLS launch-gate deployment.');

test('release bundle uses HTTPS API, Secure cookies, CORS, refresh and streamed activity through the proxy', async ({ page, context }) => {
  const api = 'https://api.launchgate.example.org:19443';
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`tls_${randomUUID().slice(0, 12)}`);
  await page.getByLabel('Password', { exact: true }).fill('Synthetic-HTTPS-password-2026!');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  const cookie = (await context.cookies(api + '/api/v1/auth/me')).find(item => item.name === 'mentra_session');
  expect(cookie?.secure).toBe(true);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe('Lax');
  expect(cookie?.path).toBe('/api/v1');
  expect(await page.evaluate(() => document.cookie)).not.toContain('mentra_session');
  await page.reload();
  await expect(page.getByLabel('Ask Mentra anything')).toBeEnabled();
  const probe = await page.evaluate(async (apiOrigin) => {
    const response = await fetch(apiOrigin + '/api/v1/auth/me', { credentials: 'include' });
    return { status: response.status, cache: response.headers.get('cache-control') };
  }, api);
  expect(probe).toEqual({ status: 200, cache: 'no-store' });
  const body = { conversation_id: randomUUID(), client_turn_id: randomUUID(), expected_revision: 0, content: 'Hello!' };
  const stream = await page.evaluate(async ({ apiOrigin, turn }) => {
    const response = await fetch(apiOrigin + '/api/v1/conversations/turns?stream=true', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(turn) });
    if (!response.ok) throw new Error('Turn submission failed: ' + response.status);
    const events = await fetch(`${apiOrigin}/api/v1/conversations/${turn.conversation_id}/turns/${turn.client_turn_id}/events`, { credentials: 'include' });
    const text = await events.text();
    return { status: events.status, type: events.headers.get('content-type'), terminal: text.includes('event: terminal'), success: text.includes('SUCCEEDED') };
  }, { apiOrigin: api, turn: body });
  expect(stream.status).toBe(200);
  expect(stream.type).toContain('text/event-stream');
  expect(stream.terminal).toBe(true);
  expect(stream.success).toBe(true);
  const deepLink = await page.goto('/settings');
  expect(deepLink?.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
});
