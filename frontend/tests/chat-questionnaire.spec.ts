import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

for (const mobile of [false, true]) test(`five chat questions submit together and survive reload ${mobile ? 'mobile' : 'desktop'}`, async ({ page }, testInfo) => {
  test.setTimeout(100_000);
  if (mobile) await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`group_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('isolated grouped conversation password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  const composer = page.getByRole('textbox', { name: 'Ask Mentra anything' });
  await composer.fill('Show five getting-started questions');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const group = page.getByRole('region', { name: 'Conversation questions' });
  await expect(group).toBeVisible();
  await expect(group.getByRole('navigation', { name: 'Conversation questions' }).getByRole('button')).toHaveCount(5);
  await expect(group.getByRole('button', { name: 'Submit all answers', exact: true })).toHaveCount(1);
  await expect(group.getByRole('button', { name: 'Submit all answers' })).toBeDisabled();
  await group.getByRole('radio', { name: 'Other goal', exact: true }).check();
  await group.getByLabel('Your goal', { exact: true }).fill('Work presentations');
  await group.getByRole('button', { name: 'Next', exact: true }).click();
  await group.getByRole('radio', { name: '30 minutes', exact: true }).check();
  await group.getByRole('button', { name: 'Next', exact: true }).click();
  await group.getByRole('checkbox', { name: 'Listening', exact: true }).check();
  await group.getByRole('checkbox', { name: 'Speaking', exact: true }).check();
  await group.getByRole('button', { name: 'Next', exact: true }).click();
  await group.getByRole('radio', { name: 'Step by step', exact: true }).check();
  await group.getByRole('button', { name: 'Next', exact: true }).click();
  await group.getByRole('textbox', { name: 'Your answer', exact: true }).fill('Slow pace please.');
  await group.getByRole('button', { name: 'Go to question 1, answered' }).click();
  await expect(group.getByLabel('Your goal', { exact: true })).toHaveValue('Work presentations');
  const sent: unknown[] = [];
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().includes('/conversations/turns')) {
      const body = request.postDataJSON(); if (body.interaction_response) sent.push(body.interaction_response);
    }
  });
  await page.screenshot({ path: testInfo.outputPath('questionnaire.png'), fullPage: true });
  await group.getByRole('button', { name: 'Submit all answers', exact: true }).click();
  await expect(page.getByText('Received all five answers together.', { exact: true })).toBeVisible({ timeout: 25000 });
  expect(sent).toHaveLength(1);
  expect(Object.keys((sent[0] as { answers: object }).answers)).toHaveLength(5);
  await expect(group.getByText('All answers submitted.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(group.getByText('All answers submitted.', { exact: true })).toBeVisible();
  await expect(group.getByRole('button', { name: 'Submit all answers' })).toHaveCount(0);
  await group.getByRole('button', { name: 'Go to question 1, answered' }).click();
  await expect(group.getByLabel('Your goal', { exact: true })).toHaveValue('Work presentations');
  await expect(group.getByLabel('Your goal', { exact: true })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  const library = await page.request.get('http://127.0.0.1:18003/api/v1/assessments');
  expect((await library.json()).items).toHaveLength(0);
});

test('five legacy cards use one batch submission', async ({ page }) => {
  test.setTimeout(90000);
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`legacy_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('isolated legacy batch password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Show five legacy questions');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const group = page.getByRole('region', { name: 'Conversation questions' });
  for (let i = 1; i <= 5; i++) {
    await group.getByRole('radio', { name: `Choice A ${i}`, exact: true }).check();
    if (i < 5) await group.getByRole('button', { name: 'Next', exact: true }).click();
  }
  const response = page.waitForRequest(request => request.method() === 'POST' && request.url().includes('/conversations/turns'));
  await group.getByRole('button', { name: 'Submit all answers', exact: true }).click();
  expect((await response).postDataJSON().interaction_response.additional_responses).toHaveLength(4);
  await expect(page.getByText('Received all legacy answers together.', { exact: true })).toBeVisible({ timeout: 25000 });
});
