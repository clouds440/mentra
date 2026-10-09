import { chooseOption } from './select-helpers';
import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { fillProfile } from './profile-helpers';

const credentials = () => ({ username: `profile_${randomUUID().slice(0, 8)}`, password: 'a long profile passphrase' });
async function register(page: import('@playwright/test').Page) {
  const account = credentials();
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(account.username);
  await page.getByLabel('Password', { exact: true }).fill(account.password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByRole('heading', { name: 'Make Mentra yours' })).toBeVisible();
  return account;
}

test('information is mandatory and optional calibration resumes across refresh and login', async ({ page }) => {
  const account = await register(page);
  await expect(page.getByRole('button', { name: /skip/i })).toHaveCount(0);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByText('Select your education level.')).toBeVisible();
  await page.goto('/settings');
  await expect(page).toHaveURL(/\/onboarding$/);
  await fillProfile(page);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'A quick starting point' })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByLabel('Username', { exact: true }).fill(account.username);
  await page.getByLabel('Password', { exact: true }).fill(account.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A quick starting point' })).toBeVisible();
  await page.getByRole('button', { name: 'Skip for now', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible();
  await page.goto('/settings');
  await expect(page.getByText('Not yet estimated', { exact: true })).toHaveCount(5);
  await expect(page.getByRole('link', { name: 'Start calibration', exact: true })).toBeVisible();
});

test('calibration submits together, evaluates results, and profile preferences remain editable', async ({ page, context }) => {
  await register(page);
  await fillProfile(page, 'undergraduate', 'Computer science');
  await page.getByRole('button', { name: 'Start quick calibration', exact: true }).click();
  await expect(page.getByText('Question 1 of 8', { exact: true })).toBeVisible();
  await page.getByRole('group', { name: 'Answer choices' }).locator('label').first().click();
  await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Question 2 of 8', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Question 1 of 8', { exact: true })).toBeVisible();
  await page.getByRole('group', { name: 'Answer choices' }).locator('label').first().click();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Question 2 of 8', { exact: true })).toBeVisible();
  for (let index = 2; index <= 8; index++) {
    await expect(page.getByText(`Question ${index} of 8`, { exact: true })).toBeVisible();
    await page.getByRole('group', { name: 'Answer choices' }).locator('label').first().click();
    const next = page.getByRole('button', { name: index === 8 ? 'Finish calibration' : 'Next', exact: true });
    await expect(next).toBeEnabled();
    await next.click();
  }
  await expect(page.getByRole('heading', { name: 'Your starting point is ready' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Broad proficiency estimates' })).toBeVisible();
  const backend = await context.request.get('http://127.0.0.1:18003/api/v1/student-profile');
  const before = await backend.json();
  expect(before.evaluation_status).toBe('applied');
  expect(before.details.education_level).toBe('undergraduate');
  expect(before.estimates.reasoning.evidence_count).toBe(2);
  await page.getByRole('button', { name: 'Enter Mentra' }).click();
  await page.goto('/settings');
  await page.getByRole('button', { name: 'Edit profile' }).click();
  await chooseOption(page.getByLabel('Learning preference', { exact: true }), 'concise');
  await chooseOption(page.getByLabel('Explanation depth', { exact: true }), 'brief');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByRole('button', { name: 'Edit profile' })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Concise / direct', { exact: true })).toBeVisible();
  const after = await (await context.request.get('http://127.0.0.1:18003/api/v1/student-profile')).json();
  expect(after.details.learning_preference).toBe('concise');
  expect(after.estimates).toEqual(before.estimates);
});

test('skipped calibration can be completed later in settings and uses level-appropriate questions', async ({ page }) => {
  await register(page);
  await fillProfile(page, 'primary');
  await page.getByRole('button', { name: 'Skip for now', exact: true }).click();
  await page.goto('/settings');
  await page.getByRole('link', { name: 'Start calibration' }).click();
  await expect(page).toHaveURL(/\/calibration$/);
  await page.getByRole('button', { name: 'Start quick calibration', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'The pattern is circle, square, circle, square. What comes next?' })).toBeVisible();
  await page.getByRole('group', { name: 'Answer choices' }).getByText('Circle', { exact: true }).click();
  await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Back', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Skip calibration for now', exact: true }).click();
  await expect(page).toHaveURL(/\/settings$/);
});

test('a failed final submission preserves local choices for a single bulk retry', async ({ page, context }) => {
  await register(page);
  await fillProfile(page);
  await page.getByRole('button', { name: 'Start quick calibration' }).click();
  await expect(page.getByText('Question 1 of 8', { exact: true })).toBeVisible();
  await page.route('**/api/v1/student-profile/calibration/*/complete', async (route) => {
    expect(Object.keys(route.request().postDataJSON().answers)).toHaveLength(8);
    await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
  }, { times: 1 });
  for (let index = 1; index <= 8; index++) {
    await expect(page.getByText(`Question ${index} of 8`, { exact: true })).toBeVisible();
    await page.getByRole('group', { name: 'Answer choices' }).locator('label').first().click();
    await page.getByRole('button', { name: index === 8 ? 'Finish calibration' : 'Next', exact: true }).click();
  }
  await expect(page.getByRole('button', { name: 'Reload assessment' })).toBeVisible();
  const endpoint = 'http://127.0.0.1:18003/api/v1/student-profile/calibration';
  const saved = await (await context.request.get(endpoint)).json();
  expect(Object.keys(saved.answers)).toHaveLength(0);
  await page.getByRole('button', { name: 'Reload assessment' }).click();
  await expect(page.getByRole('radio').first()).toBeChecked();
  await page.getByRole('button', { name: 'Finish calibration', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your starting point is ready' })).toBeVisible();
  expect(Object.keys((await (await context.request.get(endpoint)).json()).answers)).toHaveLength(8);
});

test('selection and navigation stay local and stable until one bulk submission', async ({ page, context }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await register(page);
  await fillProfile(page);
  await page.getByRole('button', { name: 'Start quick calibration' }).click();
  await expect(page.getByText('Question 1 of 8', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 320, height: 568 });
  const group = page.getByRole('group', { name: 'Answer choices' });
  const assessment = page.getByRole('region', { name: 'Calibration assessment' });
  let saves = 0;
  await page.route('**/api/v1/student-profile/calibration/*/answers', async (route) => {
    saves++;
    await route.continue();
  });
  const before = await group.boundingBox();
  await group.locator('label').first().click();
  await expect(page.getByRole('radio').first()).toBeChecked();
  await group.locator('label').nth(1).click();
  await expect(page.getByRole('radio').nth(1)).toBeChecked();
  await expect(assessment).toHaveAttribute('aria-busy', 'false');
  await expect(page.getByRole('radio').first()).toBeEnabled();
  const after = await group.boundingBox();
  expect(after?.height).toBe(before?.height);
  expect(after?.width).toBe(before?.width);
  expect(saves).toBe(0);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Question 2 of 8', { exact: true })).toBeVisible();
  await group.locator('label').nth(2).click();
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(page.getByRole('radio').nth(1)).toBeChecked();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Question 2 of 8', { exact: true })).toBeVisible();
  await expect(page.getByRole('radio').nth(2)).toBeChecked();
  expect(saves).toBe(0);
  for (const width of [320, 375, 768, 1440]) {
    await page.setViewportSize({ width, height: 568 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeEnabled();
  }
  const endpoint = 'http://127.0.0.1:18003/api/v1/student-profile/calibration';
  expect(Object.keys((await (await context.request.get(endpoint)).json()).answers)).toHaveLength(0);
  await page.setViewportSize({ width: 320, height: 568 });
  let submissions = 0;
  await page.route('**/api/v1/student-profile/calibration/*/complete', async (route) => {
    submissions++;
    expect(Object.keys(route.request().postDataJSON().answers)).toHaveLength(8);
    await route.continue();
  });
  for (let index = 2; index <= 8; index++) {
    await group.locator('label').first().click();
    await page.getByRole('button', { name: index === 8 ? 'Finish calibration' : 'Next', exact: true }).click();
  }
  await expect(page.getByRole('heading', { name: 'Your starting point is ready' })).toBeVisible();
  expect(saves).toBe(0);
  expect(submissions).toBe(1);
});

test('AI outage preserves answers, leaves estimates unknown, and evaluation can be retried', async ({ page, context }) => {
  await context.request.post('http://127.0.0.1:18003/testing/profile-evaluator', { data: { mode: 'unavailable' } });
  try {
    await register(page);
    await fillProfile(page);
    await page.getByRole('button', { name: 'Start quick calibration' }).click();
    for (let index = 1; index <= 8; index++) {
      await expect(page.getByText(`Question ${index} of 8`, { exact: true })).toBeVisible();
      await page.getByRole('group', { name: 'Answer choices' }).locator('label').first().click();
      const next = page.getByRole('button', { name: index === 8 ? 'Finish calibration' : 'Next', exact: true });
      await expect(next).toBeEnabled();
      await next.click();
    }
    await expect(page.getByRole('heading', { name: 'Your answers are saved' })).toBeVisible();
    await expect(page.getByText('Not yet estimated', { exact: true })).toHaveCount(5);
    await page.getByRole('button', { name: 'Enter Mentra' }).click();
    await page.goto('/settings');
    await expect(page.getByRole('button', { name: 'Retry evaluation', exact: true })).toBeVisible();
    await context.request.post('http://127.0.0.1:18003/testing/profile-evaluator', { data: { mode: 'available' } });
    await page.getByRole('button', { name: 'Retry evaluation', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Retry evaluation', exact: true })).toHaveCount(0);
    await expect(page.getByText('Not yet estimated', { exact: true })).toHaveCount(0);
  } finally {
    await context.request.post('http://127.0.0.1:18003/testing/profile-evaluator', { data: { mode: 'available' } });
  }
});

for (const theme of ['light', 'dark'] as const) {
  test(`profile onboarding fits narrow and wide screens in ${theme} theme`, async ({ page }, testInfo) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await register(page);
    for (const width of [320, 768, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.screenshot({ path: testInfo.outputPath(`profile-${theme}-${width}.png`), fullPage: true });
    }
    await fillProfile(page, 'graduate', 'Physics');
    await page.setViewportSize({ width: 320, height: 568 });
    await page.getByRole('button', { name: 'Start quick calibration' }).click();
    await expect(page.getByText('Question 1 of 8', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`assessment-${theme}-320.png`), fullPage: true });
  });
}
